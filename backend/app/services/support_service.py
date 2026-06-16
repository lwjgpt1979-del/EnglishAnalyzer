"""客服工单（§13.1）：用户在线咨询，后台客服受理/回复/结案。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SupportMessage, SupportTicket

_CATEGORIES = {"refund", "feature", "complaint", "order", "other"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ticket_item(t: SupportTicket, *, unread_for: str | None = None,
                 last_content: str | None = None) -> dict:
    return {
        "id": str(t.id), "user_id": str(t.user_id), "category": t.category,
        "subject": t.subject, "status": t.status, "last_reply_role": t.last_reply_role,
        "order_id": str(t.order_id) if t.order_id else None,
        "last_content": last_content,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _msg_item(m: SupportMessage) -> dict:
    return {
        "id": str(m.id), "sender_role": m.sender_role, "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── 用户侧 ──────────────────────────────────────────────────────────────────
async def create_ticket(db: AsyncSession, *, user_id: uuid.UUID, category: str,
                        subject: str, content: str,
                        order_id: uuid.UUID | None = None) -> SupportTicket:
    if category not in _CATEGORIES:
        raise AppError(code=400, message="无效的工单类型")
    subject = (subject or "").strip()
    content = (content or "").strip()
    if not subject or not content:
        raise AppError(code=400, message="标题和内容不能为空")
    t = SupportTicket(
        id=uuid.uuid4(), user_id=user_id, category=category, subject=subject[:120],
        status="open", last_reply_role="user", order_id=order_id)
    db.add(t)
    await db.flush()
    db.add(SupportMessage(id=uuid.uuid4(), ticket_id=t.id, sender_role="user",
                          sender_id=user_id, content=content))
    await db.flush()
    return t


async def list_mine(db: AsyncSession, *, user_id: uuid.UUID,
                    skip: int = 0, limit: int = 50) -> dict:
    stmt = select(SupportTicket).where(SupportTicket.user_id == user_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(SupportTicket.updated_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_ticket_item(t) for t in rows]}


async def get_thread(db: AsyncSession, *, ticket_id: uuid.UUID,
                     user_id: uuid.UUID | None = None) -> dict:
    """读取工单及全部消息。user_id 非空时校验归属（防越权）。"""
    t = await db.get(SupportTicket, ticket_id)
    if t is None:
        raise AppError(code=404, message="工单不存在")
    if user_id is not None and t.user_id != user_id:
        raise AppError(code=403, message="无权查看该工单")
    msgs = (await db.execute(
        select(SupportMessage).where(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at.asc()))).scalars().all()
    return {"ticket": _ticket_item(t), "messages": [_msg_item(m) for m in msgs]}


async def reply(db: AsyncSession, *, ticket_id: uuid.UUID, sender_role: str,
                sender_id: uuid.UUID, content: str) -> SupportMessage:
    content = (content or "").strip()
    if not content:
        raise AppError(code=400, message="回复内容不能为空")
    t = await db.get(SupportTicket, ticket_id)
    if t is None:
        raise AppError(code=404, message="工单不存在")
    if t.status == "closed":
        raise AppError(code=400, message="工单已结案，无法回复")
    if sender_role == "user" and t.user_id != sender_id:
        raise AppError(code=403, message="无权回复该工单")
    m = SupportMessage(id=uuid.uuid4(), ticket_id=ticket_id, sender_role=sender_role,
                       sender_id=sender_id, content=content)
    db.add(m)
    t.last_reply_role = sender_role
    t.status = "replied" if sender_role == "admin" else "open"
    t.updated_at = _now()
    await db.flush()
    # 客服回复 → 通知用户
    if sender_role == "admin":
        from app.services import notification_service
        await notification_service.emit(
            db, user_id=t.user_id, type_="system", title="客服已回复您的工单",
            content=f"「{t.subject}」客服已回复，点击查看。",
            meta={"ticket_id": str(ticket_id)})
    return m


# ── 管理侧 ──────────────────────────────────────────────────────────────────
async def admin_list(db: AsyncSession, *, status: str = "open", category: str = "all",
                     skip: int = 0, limit: int = 50) -> dict:
    stmt = select(SupportTicket)
    if status and status != "all":
        if status == "pending":   # 待客服处理：open 或 用户最后说话
            stmt = stmt.where(SupportTicket.status != "closed",
                              SupportTicket.last_reply_role == "user")
        else:
            stmt = stmt.where(SupportTicket.status == status)
    if category and category != "all":
        stmt = stmt.where(SupportTicket.category == category)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(SupportTicket.updated_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_ticket_item(t) for t in rows]}


async def close_ticket(db: AsyncSession, *, ticket_id: uuid.UUID,
                       admin_id: uuid.UUID) -> SupportTicket:
    t = await db.get(SupportTicket, ticket_id)
    if t is None:
        raise AppError(code=404, message="工单不存在")
    t.status = "closed"
    t.handled_by = admin_id
    t.updated_at = _now()
    await db.flush()
    return t


async def stats(db: AsyncSession) -> dict:
    """大盘用：待处理工单数。"""
    pending = int(await db.scalar(
        select(func.count()).select_from(SupportTicket).where(
            SupportTicket.status != "closed",
            SupportTicket.last_reply_role == "user")) or 0)
    return {"pending": pending}
