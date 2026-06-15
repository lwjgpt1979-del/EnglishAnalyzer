"""发票申请记录（§5.4）：用户申请开票 + 后台开具/驳回。

应用内只管"申请 + 状态"；真实发票由税控/电子发票服务商开具后回填 invoice_no/url。
开票方=订单收款主体（payment_account_id），主体演进后由对应实体开票。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import InvoiceRequest, Order
from app.models.d10_branch import PaymentAccount


def _item(r: InvoiceRequest, *, account_name: str | None = None,
          order_no: str | None = None) -> dict:
    return {
        "id": str(r.id), "order_id": str(r.order_id), "order_no": order_no,
        "payment_account": account_name,
        "title_type": r.title_type, "title": r.title, "tax_no": r.tax_no,
        "amount_yuan": round((r.amount_fen or 0) / 100, 2),
        "content": r.content, "email": r.email, "status": r.status,
        "invoice_no": r.invoice_no, "invoice_url": r.invoice_url, "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "issued_at": r.issued_at.isoformat() if r.issued_at else None,
    }


async def request_invoice(db: AsyncSession, *, user_id: uuid.UUID, order_id: uuid.UUID,
                          title_type: str, title: str, tax_no: str | None,
                          content: str | None, email: str | None) -> InvoiceRequest:
    """用户对已支付订单申请开票。"""
    order = await db.get(Order, order_id)
    if order is None or order.beneficiary_id != user_id and order.payer_id != user_id:
        raise AppError(code=404, message="订单不存在")
    if order.status not in ("paid", "partial_refunded"):
        raise AppError(code=400, message="仅已支付订单可申请开票")
    if not (title or "").strip():
        raise AppError(code=400, message="发票抬头必填")
    if title_type == "company" and not (tax_no or "").strip():
        raise AppError(code=400, message="企业抬头需填写税号")
    # 已有 pending/issued 申请则不重复（驳回后可重申）
    existing = await db.scalar(select(InvoiceRequest).where(and_(
        InvoiceRequest.order_id == order_id,
        InvoiceRequest.status.in_(("pending", "issued")))))
    if existing is not None:
        raise AppError(code=400, message="该订单已申请开票，请勿重复提交")
    rec = InvoiceRequest(
        id=uuid.uuid4(), user_id=user_id, order_id=order_id,
        payment_account_id=order.payment_account_id,
        title_type=title_type, title=title.strip(), tax_no=(tax_no or "").strip() or None,
        amount_fen=order.amount_fen, content=(content or "会员服务费"),
        email=(email or "").strip() or None, status="pending")
    db.add(rec)
    await db.flush()
    return rec


async def list_mine(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(InvoiceRequest, Order.order_no)
        .join(Order, InvoiceRequest.order_id == Order.id)
        .where(InvoiceRequest.user_id == user_id)
        .order_by(InvoiceRequest.created_at.desc()))).all()
    return [_item(r, order_no=on) for r, on in rows]


# ── 后台 ──────────────────────────────────────────────────────────────────────

async def admin_list(db: AsyncSession, *, status: str = "pending",
                     skip: int = 0, limit: int = 50) -> dict:
    stmt = (select(InvoiceRequest, Order.order_no, PaymentAccount.name)
            .join(Order, InvoiceRequest.order_id == Order.id)
            .join(PaymentAccount, InvoiceRequest.payment_account_id == PaymentAccount.id, isouter=True))
    if status and status != "all":
        stmt = stmt.where(InvoiceRequest.status == status)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(InvoiceRequest.created_at.desc()).offset(skip).limit(limit))).all()
    return {"total": total,
            "items": [_item(r, account_name=an, order_no=on) for r, on, an in rows]}


async def issue(db: AsyncSession, *, invoice_id: uuid.UUID, admin_id: uuid.UUID,
                invoice_no: str, invoice_url: str | None) -> InvoiceRequest:
    rec = await db.get(InvoiceRequest, invoice_id)
    if rec is None:
        raise AppError(code=404, message="开票申请不存在")
    if not (invoice_no or "").strip():
        raise AppError(code=400, message="请填写发票号码")
    rec.status = "issued"
    rec.invoice_no = invoice_no.strip()
    rec.invoice_url = (invoice_url or "").strip() or None
    rec.issued_by = admin_id
    rec.issued_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()
    return rec


async def reject(db: AsyncSession, *, invoice_id: uuid.UUID, note: str | None) -> InvoiceRequest:
    rec = await db.get(InvoiceRequest, invoice_id)
    if rec is None:
        raise AppError(code=404, message="开票申请不存在")
    rec.status = "rejected"
    rec.note = (note or "").strip() or None
    await db.flush()
    return rec
