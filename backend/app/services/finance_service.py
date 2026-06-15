"""财务管理（§5.4）：营收统计 + 订单明细 + CSV 导出 + 分公司分成结算。

按 **收款主体(payment_account)** 与 **分公司(branch_company)** 两个维度聚合，
天然适配主体演进（个体 → 公司承接 → 总公司+地方子公司）：换主体=多一行，零改代码。
口径：营收=周期内已支付订单金额；退款=周期内已完成退款金额；净收入=营收-退款。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import Order, RefundRecord
from app.models.d10_branch import BranchCompany, BranchSettlement, PaymentAccount


def _yuan(fen: int | None) -> float:
    return round((fen or 0) / 100, 2)


async def _gross_by(db: AsyncSession, col, start, end) -> dict:
    """周期内已支付订单按 col 分组的金额与单数。"""
    rows = (await db.execute(
        select(col, func.coalesce(func.sum(Order.amount_fen), 0), func.count())
        .where(and_(Order.status.in_(("paid", "refunded", "partial_refunded")),
                    Order.paid_at >= start, Order.paid_at < end))
        .group_by(col)
    )).all()
    return {str(k) if k else None: {"gross": int(g or 0), "orders": int(c or 0)} for k, g, c in rows}


async def _refund_by(db: AsyncSession, col, start, end) -> dict:
    """周期内已完成退款按订单的 col 分组（refund→order 关联）。"""
    rows = (await db.execute(
        select(col, func.coalesce(func.sum(RefundRecord.amount_fen), 0), func.count())
        .select_from(RefundRecord).join(Order, RefundRecord.order_id == Order.id)
        .where(and_(RefundRecord.status == "completed",
                    RefundRecord.reviewed_at >= start, RefundRecord.reviewed_at < end))
        .group_by(col)
    )).all()
    return {str(k) if k else None: {"refund": int(r or 0), "refunds": int(c or 0)} for k, r, c in rows}


async def revenue_summary(db: AsyncSession, *, start: dt.datetime, end: dt.datetime,
                          group_by: str = "account") -> dict:
    """营收统计。group_by: account(收款主体) | branch(分公司) | none(总计)。"""
    if group_by == "branch":
        col = Order.branch_company_id
        names = {str(b.id): b.name for b in (await db.execute(select(BranchCompany))).scalars()}
        none_label = "未归属分公司（总部）"
    else:
        col = Order.payment_account_id
        names = {str(a.id): a.name for a in (await db.execute(select(PaymentAccount))).scalars()}
        none_label = "未指定收款主体"

    gross = await _gross_by(db, col, start, end)
    refund = await _refund_by(db, col, start, end)
    keys = set(gross) | set(refund)
    groups = []
    tot_g = tot_r = tot_o = tot_rf = 0
    for k in keys:
        g = gross.get(k, {}).get("gross", 0)
        o = gross.get(k, {}).get("orders", 0)
        rf_fen = refund.get(k, {}).get("refund", 0)
        rf_cnt = refund.get(k, {}).get("refunds", 0)
        tot_g += g; tot_r += rf_fen; tot_o += o; tot_rf += rf_cnt
        groups.append({
            "key": k, "name": names.get(k, none_label),
            "gross_yuan": _yuan(g), "refund_yuan": _yuan(rf_fen), "net_yuan": _yuan(g - rf_fen),
            "orders": o, "refunds": rf_cnt,
        })
    groups.sort(key=lambda x: x["gross_yuan"], reverse=True)
    return {
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "group_by": group_by,
        "total": {"gross_yuan": _yuan(tot_g), "refund_yuan": _yuan(tot_r),
                  "net_yuan": _yuan(tot_g - tot_r), "orders": tot_o, "refunds": tot_rf},
        "groups": groups,
    }


async def list_orders(db: AsyncSession, *, start: dt.datetime, end: dt.datetime,
                      skip: int = 0, limit: int = 100) -> dict:
    """订单明细（周期内已支付），供财务核对。"""
    base = select(Order).where(and_(
        Order.status.in_(("paid", "refunded", "partial_refunded")),
        Order.paid_at >= start, Order.paid_at < end))
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (await db.execute(
        base.order_by(Order.paid_at.desc()).offset(skip).limit(limit))).scalars().all()
    acc_names = {str(a.id): a.name for a in (await db.execute(select(PaymentAccount))).scalars()}
    items = [{
        "order_no": o.order_no, "tier": str(o.tier), "amount_yuan": _yuan(o.amount_fen),
        "status": o.status, "refund_status": o.refund_status,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "payment_account": acc_names.get(str(o.payment_account_id), "-"),
    } for o in rows]
    return {"total": total, "items": items}


async def export_orders_csv(db: AsyncSession, *, start: dt.datetime, end: dt.datetime) -> str:
    """导出周期内订单明细 CSV（财务/会计用）。"""
    data = await list_orders(db, start=start, end=end, skip=0, limit=100000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["订单号", "档位", "金额(元)", "状态", "退款状态", "支付时间", "收款主体"])
    for it in data["items"]:
        w.writerow([it["order_no"], it["tier"], it["amount_yuan"], it["status"],
                    it["refund_status"], it["paid_at"], it["payment_account"]])
    return buf.getvalue()


# ── 分公司分成结算（§5.4 机构结算）──────────────────────────────────────────────

async def compute_settlement(db: AsyncSession, *, branch_id: uuid.UUID,
                             start: dt.date, end: dt.date, persist: bool = False) -> dict:
    """计算某分公司某周期的分成结算：净收入 × 分成率 = 分公司应得。"""
    branch = await db.get(BranchCompany, branch_id)
    if branch is None:
        raise AppError(code=404, message="分公司不存在")
    rate = float(branch.commission_rate) if branch.commission_rate is not None else 0.0
    s_dt = dt.datetime.combine(start, dt.time.min, dt.timezone.utc)
    e_dt = dt.datetime.combine(end, dt.time.min, dt.timezone.utc)
    gross = int(await db.scalar(
        select(func.coalesce(func.sum(Order.amount_fen), 0)).where(and_(
            Order.branch_company_id == branch_id,
            Order.status.in_(("paid", "refunded", "partial_refunded")),
            Order.paid_at >= s_dt, Order.paid_at < e_dt))) or 0)
    refund = int(await db.scalar(
        select(func.coalesce(func.sum(RefundRecord.amount_fen), 0))
        .select_from(RefundRecord).join(Order, RefundRecord.order_id == Order.id)
        .where(and_(Order.branch_company_id == branch_id,
                    RefundRecord.status == "completed",
                    RefundRecord.reviewed_at >= s_dt, RefundRecord.reviewed_at < e_dt))) or 0)
    net = gross - refund
    branch_payable = int(net * rate)
    platform_share = net - branch_payable
    result = {
        "branch_company_id": str(branch_id), "branch_name": branch.name,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "gross_yuan": _yuan(gross), "refund_yuan": _yuan(refund), "net_yuan": _yuan(net),
        "commission_rate": rate, "branch_payable_yuan": _yuan(branch_payable),
        "platform_share_yuan": _yuan(platform_share),
    }
    if persist:
        db.add(BranchSettlement(
            id=uuid.uuid4(), branch_company_id=branch_id, period_start=start, period_end=end,
            gross_revenue_fen=gross, refund_deduction_fen=refund, net_revenue_fen=net,
            platform_share_fen=platform_share, branch_payable_fen=branch_payable,
            commission_rate_snapshot=rate, status="draft"))
        await db.flush()
        result["persisted"] = True
    return result


async def list_settlements(db: AsyncSession, *, branch_id: uuid.UUID | None = None) -> list[dict]:
    stmt = select(BranchSettlement, BranchCompany).join(
        BranchCompany, BranchSettlement.branch_company_id == BranchCompany.id)
    if branch_id:
        stmt = stmt.where(BranchSettlement.branch_company_id == branch_id)
    rows = (await db.execute(stmt.order_by(BranchSettlement.period_start.desc()))).all()
    return [{
        "id": str(s.id), "branch_name": b.name,
        "period_start": s.period_start.isoformat(), "period_end": s.period_end.isoformat(),
        "gross_yuan": _yuan(s.gross_revenue_fen), "refund_yuan": _yuan(s.refund_deduction_fen),
        "net_yuan": _yuan(s.net_revenue_fen), "branch_payable_yuan": _yuan(s.branch_payable_fen),
        "platform_share_yuan": _yuan(s.platform_share_fen), "status": str(s.status),
    } for s, b in rows]
