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


async def _wx_refund(order: Order, amount_fen: int) -> str:
    """执行微信退款，返回 wx_refund_id。

    dev-mock：未开启或未配商户证书时只生成 mock 退款单号，不真调微信。
    """
    if not settings.wechat_pay_refund_enabled:
        return f"mock_refund_{uuid.uuid4().hex[:16]}"
    # P4：真实微信退款 v3（out_refund_no/证书签名/对账）
    raise NotImplementedError("真实微信退款 API 待 P4 实现")


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
        rec.wx_refund_id = await _wx_refund(order, r["refund_fen"])
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
            rec.wx_refund_id = await _wx_refund(order, fen)
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
    items = []
    for rec, order, user in rows:
        items.append({
            "id": rec.id,
            "order_id": order.id,
            "order_no": order.order_no,
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
        rec.wx_refund_id = await _wx_refund(order, fen)
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
