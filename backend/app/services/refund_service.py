"""退款 / 申诉规则引擎（需求文档 §4.5）。

实现三层退款体系的服务端判定：
  - 7天内：未使用→自动全额退；已使用→转人工按比例退。
  - 超7天：无理由拒；有理由走申诉（4 类，重复购买可自动退）。
退款执行 `_wx_refund` 按 `settings.wechat_pay_refund_enabled` 开关：
  关 = dev-mock 只记账；开 = 真实微信退款（P4 实现）。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d2_payments import Order, RefundRecord
from app.models.d8_usage import DailyUsage
from app.models.d9_system import FeatureUsage
from app.models.d12_v2_exams import SimPracticeRecord

REFUND_WINDOW_DAYS = 7
DUPLICATE_WINDOW_HOURS = 72
ANNUAL_APPEAL_QUOTA = 1
APPEAL_USAGE_TYPE = "appeal_annual"

APPEAL_TYPES = {"SYSTEM_FAULT", "DESC_MISMATCH", "DUPLICATE_PURCHASE", "MINOR_PURCHASE"}
HIGH_TIER = "promax"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(ts: dt.datetime | None) -> dt.datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def _days_used(order: Order, now: dt.datetime) -> int:
    """购买日→申请日的自然天数（含购买当天），最小 1。"""
    base = _aware(order.paid_at) or _aware(order.created_at) or now
    used = (now.date() - base.date()).days + 1
    return max(used, 1)


def _total_days(order: Order) -> int:
    if order.total_days and order.total_days > 0:
        return order.total_days
    return max((order.duration_months or 1) * 30, 1)


def _prorated_fen(order: Order, now: dt.datetime) -> int:
    """按剩余天数比例退款，向下取整到分。"""
    total = _total_days(order)
    used = _days_used(order, now)
    remaining = max(total - used, 0)
    return (order.amount_fen * remaining) // total


async def _used_since(db: AsyncSession, order: Order) -> int:
    """派生该订单生效后受益人是否使用过付费能力（返回计数，>0 即已使用）。

    不为每个功能埋 per-order 计数器，改由现有用量信号派生：
      - sim_practice_records（练习/出题作答）created_at > paid_at
      - feature_usage（权益配额计数）updated_at > paid_at 且 count>0
    """
    since = _aware(order.paid_at) or _aware(order.created_at)
    if since is None:
        return 0
    uid = order.beneficiary_id

    n1 = await db.scalar(
        select(func.count()).select_from(SimPracticeRecord).where(
            and_(SimPracticeRecord.student_id == uid,
                 SimPracticeRecord.created_at > since)
        )
    ) or 0
    n2 = await db.scalar(
        select(func.coalesce(func.sum(FeatureUsage.count), 0)).where(
            and_(FeatureUsage.user_id == uid,
                 FeatureUsage.updated_at > since)
        )
    ) or 0
    return int(n1) + int(n2)


async def _get_order_owned(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await db.get(Order, order_id)
    if order is None:
        raise AppError(code=404, message="订单不存在")
    # 退款申请须由受益人（学生本人）发起；亲人代付不可代为申请（§4.2）
    if order.beneficiary_id != user.id:
        raise AppError(code=403, message="只能对本人订单申请退款")
    if order.status not in ("paid", "partial_refunded"):
        raise AppError(code=400, message="该订单状态不可退款")
    return order


def _refund_notify_url(account_id: str | None) -> str | None:
    """退款结果通知地址：复用支付 notify 的同域 base，路径换 wx-refund。"""
    base = settings.wechat_pay_notify_url
    if not base:
        return None
    root = base.rsplit("/", 1)[0]  # .../api/v1/webhooks
    url = f"{root}/wx-refund"
    return f"{url}/{account_id}" if account_id else url


async def _wx_refund(db: AsyncSession, order: Order, amount_fen: int) -> tuple[str, str]:
    """执行退款，返回 (渠道退款单号, out_refund_no)。按订单固化的收款主体+渠道选适配器。

    - 全局开关 wechat_pay_refund_enabled 关 → dev-mock，不真调任何渠道。
    - 开 → 按 order.payment_account_id 解析主体凭证 → 对应渠道适配器退款（带退款
      结果通知地址，供异步对账）；凭证为 dev（占位密钥）时适配器内部仍返回 mock 单号。
    """
    out_refund_no = f"RF{uuid.uuid4().hex[:24]}"
    if not settings.wechat_pay_refund_enabled:
        return f"mock_refund_{uuid.uuid4().hex[:16]}", out_refund_no
    from app.services import payment_account_service
    from app.services.payment.base import get_provider
    creds = await payment_account_service.resolve_creds_for_order(db, order)
    provider = get_provider(creds.provider)
    refund_id = await provider.refund(
        creds, out_refund_no=out_refund_no, amount_fen=amount_fen,
        total_fen=order.amount_fen, transaction_id=order.wx_transaction_id,
        out_trade_no=order.order_no, notify_url=_refund_notify_url(creds.account_id))
    return refund_id, out_refund_no


def _apply_refund_amount(order: Order, amount_fen: int) -> None:
    order.status = "refunded" if amount_fen >= order.amount_fen else "partial_refunded"


async def evaluate_refund(db: AsyncSession, order: Order, user: User,
                          now: dt.datetime) -> dict:
    """7天内退款决策树（Step1-6）。返回判定结果，不落库。"""
    # Step 1 账号封禁
    if not user.is_active:
        return {"state_code": "REJECT_BANNED", "auto": False, "refund_fen": 0,
                "refund_type": None, "rejected": True}
    # Step 2 活动价
    if order.is_promotional:
        return {"state_code": "REJECT_PROMOTIONAL", "auto": False, "refund_fen": 0,
                "refund_type": None, "rejected": True}
    # Step 3 7天窗口
    paid = _aware(order.paid_at) or _aware(order.created_at) or now
    if (now - paid).days > REFUND_WINDOW_DAYS:
        return {"state_code": "REJECT_OVERTIME", "auto": False, "refund_fen": 0,
                "refund_type": None, "rejected": True, "overtime": True}
    # Step 5 使用量
    used = await _used_since(db, order)
    if used == 0:
        return {"state_code": "AUTO_FULL_REFUND", "auto": True,
                "refund_fen": order.amount_fen, "refund_type": "standard_7d",
                "rejected": False}
    # Step 6 按比例（转人工）
    fen = _prorated_fen(order, now)
    if fen < 1:
        return {"state_code": "REJECT_OVERTIME", "auto": False, "refund_fen": 0,
                "refund_type": None, "rejected": True}
    return {"state_code": "MANUAL_REVIEW_PARTIAL", "auto": False,
            "refund_fen": fen, "refund_type": "prorated", "rejected": False}


async def request_refund(db: AsyncSession, user: User,
                         order_id: uuid.UUID) -> RefundRecord:
    """用户发起普通退款（7天内）。"""
    order = await _get_order_owned(db, user, order_id)
    if order.refund_status not in ("NONE", "", None):
        raise AppError(code=400, message="该订单已有退款申请")

    now = _now()
    r = await evaluate_refund(db, order, user, now)
    order.refund_status = r["state_code"]

    if r["rejected"]:
        if r.get("overtime"):
            raise AppError(code=400, message="超过7天不支持无理由退款，如有特殊情形请走申诉")
        msg = {
            "REJECT_BANNED": "账号已封禁，不支持退款",
            "REJECT_PROMOTIONAL": "活动价订单不支持退款",
        }.get(r["state_code"], "不符合退款条件")
        await db.flush()
        raise AppError(code=400, message=msg)

    rec = RefundRecord(
        order_id=order.id,
        amount_fen=r["refund_fen"],
        refund_type=r["refund_type"],
        status="pending",
        state_code=r["state_code"],
        branch_company_id=order.branch_company_id,
    )
    if r["auto"]:
        # 7天内未使用 → 自动全额退款
        rec.wx_refund_id, rec.out_refund_no = await _wx_refund(db, order, r["refund_fen"])
        rec.status = "completed"
        rec.reviewed_at = now
        _apply_refund_amount(order, r["refund_fen"])
    # 否则 MANUAL_REVIEW_PARTIAL：pending，进人工队列待后台核定
    db.add(rec)
    await db.flush()
    return rec


async def _annual_appeal_count(db: AsyncSession, user_id: uuid.UUID,
                               now: dt.datetime) -> int:
    period = dt.date(now.year, 1, 1)
    row = await db.scalar(
        select(DailyUsage.count).where(
            and_(DailyUsage.user_id == user_id,
                 DailyUsage.usage_type == APPEAL_USAGE_TYPE,
                 DailyUsage.period == period)
        )
    )
    return int(row or 0)


async def _consume_annual_appeal(db: AsyncSession, user_id: uuid.UUID,
                                 now: dt.datetime) -> None:
    period = dt.date(now.year, 1, 1)
    existing = await db.scalar(
        select(DailyUsage).where(
            and_(DailyUsage.user_id == user_id,
                 DailyUsage.usage_type == APPEAL_USAGE_TYPE,
                 DailyUsage.period == period)
        )
    )
    if existing is None:
        db.add(DailyUsage(user_id=user_id, usage_type=APPEAL_USAGE_TYPE,
                          period=period, count=1))
    else:
        existing.count = (existing.count or 0) + 1


async def _auto_duplicate(db: AsyncSession, order: Order,
                          now: dt.datetime) -> bool:
    """重复购买自动校验：同受益人+同档位+72h 内另有订单，且本单未使用。

    72h 指两笔订单下单时间的接近度（以 created_at 为锚，对称窗口），
    与"距今多久"无关——重复购买可能在 7 天后才被发现并申诉。
    """
    if await _used_since(db, order) > 0:
        return False
    anchor = _aware(order.created_at) or _aware(order.paid_at) or now
    delta = dt.timedelta(hours=DUPLICATE_WINDOW_HOURS)
    cnt = await db.scalar(
        select(func.count()).select_from(Order).where(and_(
            Order.beneficiary_id == order.beneficiary_id,
            Order.tier == order.tier,
            Order.id != order.id,
            Order.status.in_(("paid", "partial_refunded")),
            Order.created_at >= anchor - delta,
            Order.created_at <= anchor + delta,
        ))
    ) or 0
    return int(cnt) >= 1


async def submit_appeal(db: AsyncSession, user: User, order_id: uuid.UUID,
                        appeal_type: str, note: str | None,
                        evidence_urls: list[str] | None) -> RefundRecord:
    """超7天有理由申诉（§4.5.1 Step7）。"""
    if appeal_type not in APPEAL_TYPES:
        raise AppError(code=400, message="无效的申诉类型")
    order = await _get_order_owned(db, user, order_id)
    if order.appeal_status not in ("NONE", "", None):
        raise AppError(code=400, message="该订单已提交过申诉")

    now = _now()
    # 年度申诉配额（仅超7天有理由申诉路径，与7天内退款独立计数）
    if await _annual_appeal_count(db, user.id, now) >= ANNUAL_APPEAL_QUOTA:
        raise AppError(code=400, message="当年申诉次数已用尽（每年限 1 次）")
    await _consume_annual_appeal(db, user.id, now)

    rec = RefundRecord(
        order_id=order.id,
        amount_fen=0,
        refund_type="appeal",
        status="pending",
        appeal_type=appeal_type,
        reason=note,
        evidence_urls=evidence_urls or None,
        branch_company_id=order.branch_company_id,
    )

    if appeal_type == "DUPLICATE_PURCHASE":
        if await _auto_duplicate(db, order, now):
            fen = order.amount_fen
            rec.amount_fen = fen
            rec.state_code = "AUTO_DUPLICATE_REFUND"
            rec.status = "completed"
            rec.reviewed_at = now
            rec.wx_refund_id, rec.out_refund_no = await _wx_refund(db, order, fen)
            _apply_refund_amount(order, fen)
            order.appeal_status = "AUTO_DUPLICATE_REFUND"
        else:
            rec.state_code = "REJECT_DUPLICATE_INELIGIBLE"
            rec.status = "rejected"
            rec.reviewed_at = now
            order.appeal_status = "REJECT_DUPLICATE_INELIGIBLE"
    else:
        # SYSTEM_FAULT / DESC_MISMATCH / MINOR_PURCHASE → 人工审核
        rec.state_code = "MANUAL_REVIEW_APPEAL"
        order.appeal_status = "MANUAL_REVIEW_APPEAL"

    db.add(rec)
    await db.flush()
    return rec


# ───────────────────── 后台审核（P3） ─────────────────────

async def list_reviews(db: AsyncSession, *, kind: str = "all",
                       status: str = "pending", skip: int = 0,
                       limit: int = 50) -> dict:
    """退款/申诉记录列表（含订单与用户摘要），供后台审核队列。

    kind: all | refund | appeal；status: all | pending（默认只看待审）。
    """
    stmt = select(RefundRecord, Order, User).join(
        Order, RefundRecord.order_id == Order.id
    ).join(User, Order.beneficiary_id == User.id)
    if kind == "appeal":
        stmt = stmt.where(RefundRecord.refund_type == "appeal")
    elif kind == "refund":
        stmt = stmt.where(RefundRecord.refund_type != "appeal")
    if status == "pending":
        stmt = stmt.where(RefundRecord.status == "pending")
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(await db.scalar(count_stmt) or 0)
    stmt = stmt.order_by(RefundRecord.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()
    now = _now()
    items = []
    for rec, order, user in rows:
        items.append({
            "id": rec.id,
            "order_id": order.id,
            "order_no": order.order_no,
            "overdue": _is_overdue(rec, now),
            "kind": "appeal" if rec.refund_type == "appeal" else "refund",
            "refund_type": rec.refund_type,
            "appeal_type": rec.appeal_type,
            "state_code": rec.state_code,
            "status": rec.status,
            "amount_fen": rec.amount_fen,
            "order_amount_fen": order.amount_fen,
            "reason": rec.reason,
            "evidence_urls": rec.evidence_urls or [],
            "user_nickname": user.nickname,
            "user_phone": user.phone,
            "order_tier": str(order.tier),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })
    return {"total": total, "items": items}


async def review(db: AsyncSession, admin: User, refund_id: uuid.UUID, *,
                 approve: bool, amount_fen: int | None = None,
                 reason: str | None = None) -> RefundRecord:
    """后台审核一条待处理退款/申诉。"""
    rec = await db.get(RefundRecord, refund_id)
    if rec is None:
        raise AppError(code=404, message="退款记录不存在")
    if rec.status != "pending":
        raise AppError(code=400, message="该记录已处理")
    order = await db.get(Order, rec.order_id)
    now = _now()
    is_appeal = rec.refund_type == "appeal"

    rec.reviewed_by = admin.id
    rec.reviewed_at = now
    if reason:
        rec.reason = reason

    if approve:
        fen = amount_fen if (amount_fen is not None and amount_fen > 0) else rec.amount_fen
        if fen < 1:
            raise AppError(code=400, message="退款金额必须大于 0")
        if fen > order.amount_fen:
            raise AppError(code=400, message="退款金额不能超过订单实付金额")
        rec.amount_fen = fen
        rec.status = "completed"
        rec.wx_refund_id, rec.out_refund_no = await _wx_refund(db, order, fen)
        _apply_refund_amount(order, fen)
        if is_appeal:
            rec.state_code = "APPEAL_APPROVED"
            order.appeal_status = "APPEAL_APPROVED"
        else:
            rec.state_code = "REFUND_PARTIAL_APPROVED"
            order.refund_status = "REFUND_PARTIAL_APPROVED"
    else:
        rec.status = "rejected"
        if is_appeal:
            rec.state_code = "APPEAL_REJECTED"
            order.appeal_status = "APPEAL_REJECTED"
        else:
            rec.state_code = "REFUND_REJECTED"
            order.refund_status = "REFUND_REJECTED"

    await db.flush()
    return rec


async def evidence_pack(db: AsyncSession, order_id: uuid.UUID) -> dict:
    """纠纷举证包（§4.6.4），结构化 JSON（PDF 后置 P4）。"""
    from app.models.d2_payments import PaymentConfirmLog

    order = await db.get(Order, order_id)
    if order is None:
        raise AppError(code=404, message="订单不存在")
    user = await db.get(User, order.beneficiary_id)

    confirm = None
    if order.payment_confirm_log_id:
        log = await db.get(PaymentConfirmLog, order.payment_confirm_log_id)
        if log:
            confirm = {
                "log_id": str(log.id),
                "confirmed_at": log.confirmed_at.isoformat() if log.confirmed_at else None,
                "ip_address": log.ip_address,
                "device_id": log.device_id,
                "session_id": log.session_id,
                "user_agent": log.user_agent,
                "checkbox_refund_policy": log.checkbox_refund_policy,
                "checkbox_digital_service": log.checkbox_digital_service,
                "plan_snapshot": log.plan_snapshot,
            }

    recs = (await db.execute(
        select(RefundRecord).where(RefundRecord.order_id == order_id)
        .order_by(RefundRecord.created_at.asc())
    )).scalars().all()

    used = await _used_since(db, order)

    return {
        "order": {
            "id": str(order.id),
            "order_no": order.order_no,
            "tier": str(order.tier),
            "amount_fen": order.amount_fen,
            "duration_months": order.duration_months,
            "total_days": order.total_days,
            "is_promotional": order.is_promotional,
            "status": order.status,
            "refund_status": order.refund_status,
            "appeal_status": order.appeal_status,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
        "user": {
            "id": str(user.id) if user else None,
            "nickname": user.nickname if user else None,
            "phone": user.phone if user else None,
        },
        "payment_confirm": confirm,
        "usage_count_since_paid": used,
        "refund_records": [
            {
                "id": str(r.id),
                "refund_type": r.refund_type,
                "appeal_type": r.appeal_type,
                "state_code": r.state_code,
                "status": r.status,
                "amount_fen": r.amount_fen,
                "reason": r.reason,
                "evidence_urls": r.evidence_urls or [],
                "wx_refund_id": r.wx_refund_id,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in recs
        ],
    }


# ───────────────────── 退款异步对账（微信退款结果通知） ─────────────────────

async def handle_refund_notify(db: AsyncSession, decrypted: dict) -> dict:
    """处理微信退款结果通知，按 out_refund_no 匹配并核对状态。

    decrypted 关键字段：out_refund_no、refund_id、refund_status(SUCCESS/CLOSED/ABNORMAL)。
    SUCCESS→确认退款到账(completed)；CLOSED/ABNORMAL→标记异常(state_code=REFUND_ABNORMAL)。
    """
    out_refund_no = decrypted.get("out_refund_no")
    if not out_refund_no:
        return {"matched": False, "reason": "no out_refund_no"}
    rec = await db.scalar(
        select(RefundRecord).where(RefundRecord.out_refund_no == out_refund_no)
    )
    if rec is None:
        return {"matched": False, "reason": "refund record not found"}

    status = decrypted.get("refund_status") or ""
    rec.wx_refund_status = status
    if decrypted.get("refund_id") and not rec.wx_refund_id:
        rec.wx_refund_id = decrypted["refund_id"]
    rec.reviewed_at = _now()

    if status == "SUCCESS":
        rec.status = "completed"          # 退款到账确认
    elif status in ("CLOSED", "ABNORMAL"):
        rec.state_code = "REFUND_ABNORMAL"  # 退款失败/异常，留待人工对账处理
    await db.flush()
    return {"matched": True, "refund_status": status, "record_id": str(rec.id)}


# ───────────────────── 纠纷举证包（打印即 PDF 的 HTML，§4.6.4） ─────────────────────

def _esc(v) -> str:
    import html
    return html.escape("" if v is None else str(v))


async def evidence_html(db: AsyncSession, order_id: uuid.UUID) -> str:
    """生成打印就绪的举证包 HTML（中文无字体坑；浏览器「打印为 PDF」即得带水印 PDF）。"""
    pack = await evidence_pack(db, order_id)
    o = pack["order"]; u = pack["user"]; c = pack["payment_confirm"]
    gen = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def row(k, v):
        return f'<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>'

    confirm_html = '<p class="muted">无支付确认留存记录</p>'
    if c:
        confirm_html = "<table>" + "".join([
            row("勾选时间", c.get("confirmed_at")), row("IP 地址", c.get("ip_address")),
            row("设备指纹", c.get("device_id")), row("UA", c.get("user_agent")),
            row("已勾选·退款规则", "是" if c.get("checkbox_refund_policy") else "否"),
            row("已勾选·虚拟服务", "是" if c.get("checkbox_digital_service") else "否"),
        ]) + "</table>"

    recs_html = "".join(
        f'<tr><td>{_esc(r["refund_type"])}</td><td>{_esc(r.get("appeal_type") or "-")}</td>'
        f'<td>{_esc(r["state_code"])}</td><td>{_esc(r["status"])}</td>'
        f'<td>¥{(r["amount_fen"] or 0)/100:.2f}</td><td>{_esc(r.get("wx_refund_id") or "-")}</td>'
        f'<td>{_esc(r.get("created_at"))}</td></tr>'
        for r in pack["refund_records"]) or '<tr><td colspan="7" class="muted">无</td></tr>'

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>纠纷举证包 {_esc(o['order_no'])}</title>
<style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; color: #222; font-size: 13px; position: relative; }}
.watermark {{ position: fixed; inset: 0; z-index: 0; overflow: hidden; opacity: .07; transform: rotate(-30deg); }}
.watermark div {{ font-size: 26px; white-space: nowrap; line-height: 90px; color: #000; }}
.content {{ position: relative; z-index: 1; }}
h1 {{ font-size: 20px; }} h2 {{ font-size: 15px; margin-top: 18px; border-left: 4px solid #1677ff; padding-left: 8px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; word-break: break-all; }}
th {{ background: #f5f7fa; width: 130px; font-weight: 600; }}
.muted {{ color: #999; }} .gen {{ color: #999; font-size: 11px; margin-top: 6px; }}
@media print {{ .noprint {{ display: none; }} }}
</style></head><body>
<div class="watermark">{''.join(f'<div>engGramer 举证 {gen} &nbsp; ' * 3 + '</div>' for _ in range(14))}</div>
<div class="content">
<button class="noprint" onclick="window.print()" style="float:right;padding:6px 14px">打印 / 另存为 PDF</button>
<h1>纠纷举证包</h1>
<p class="gen">生成时间：{gen}</p>

<h2>一、订单信息</h2><table>
{row("订单号", o["order_no"])}{row("档位", o["tier"])}{row("金额", f'¥{(o["amount_fen"] or 0)/100:.2f}')}
{row("时长(天)", o["total_days"])}{row("活动价", "是" if o["is_promotional"] else "否")}
{row("状态", o["status"])}{row("退款状态", o["refund_status"])}{row("申诉状态", o["appeal_status"])}
{row("支付时间", o["paid_at"])}{row("下单时间", o["created_at"])}
{row("用户", u.get("nickname"))}{row("手机", u.get("phone"))}
</table>

<h2>二、支付前合规确认留存</h2>{confirm_html}

<h2>三、会员使用记录</h2><table>{row("生效后使用次数", pack["usage_count_since_paid"])}</table>

<h2>四、退款 / 申诉记录</h2>
<table><tr><th>类型</th><th>申诉类型</th><th>状态码</th><th>状态</th><th>金额</th><th>渠道退款单号</th><th>时间</th></tr>
{recs_html}</table>
</div></body></html>"""


# ───────────────────── 退款/申诉 SLA 超时告警（§4.5.3） ─────────────────────
# 人工审核 SLA：7天内已使用按比例退款 + 超7天申诉，均要求 3 个工作日内处理。
# 简化为 3 个自然日；超时即纳入告警。
SLA_DAYS = 3


def _is_overdue(rec, now: dt.datetime) -> bool:
    if rec.status != "pending":
        return False
    created = _aware(rec.created_at) or now
    return (now - created).days >= SLA_DAYS


async def find_overdue(db: AsyncSession) -> list[dict]:
    """待处理且超 SLA 的退款/申诉记录。"""
    now = _now()
    rows = (await db.execute(
        select(RefundRecord, Order.order_no)
        .join(Order, RefundRecord.order_id == Order.id)
        .where(RefundRecord.status == "pending")
        .order_by(RefundRecord.created_at.asc()))).all()
    out = []
    for rec, order_no in rows:
        if _is_overdue(rec, now):
            created = _aware(rec.created_at) or now
            out.append({
                "id": str(rec.id), "order_no": order_no,
                "kind": "appeal" if rec.refund_type == "appeal" else "refund",
                "days_overdue": (now - created).days,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            })
    return out


async def run_sla_alerts(db: AsyncSession) -> dict:
    """扫描超 SLA 的待处理退款/申诉，向平台管理员发站内告警。"""
    overdue = await find_overdue(db)
    if not overdue:
        return {"overdue": 0, "admins_notified": 0}
    from app.models.d1_users import User
    from app.services import notification_service
    admin_ids = (await db.execute(
        select(User.id).where(User.role == "platform_admin", User.is_active.is_(True)))).scalars().all()
    max_days = max(o["days_overdue"] for o in overdue)
    title = f"⏰ {len(overdue)} 笔退款/申诉超时未处理"
    content = (f"有 {len(overdue)} 笔待处理退款/申诉已超 {SLA_DAYS} 天 SLA"
               f"（最长 {max_days} 天），请尽快在「退款/申诉审核」处理。")
    for aid in admin_ids:
        await notification_service.emit(
            db, user_id=aid, type_="system", title=title, content=content,
            meta={"kind": "refund_sla", "count": len(overdue)})
    return {"overdue": len(overdue), "admins_notified": len(admin_ids)}
