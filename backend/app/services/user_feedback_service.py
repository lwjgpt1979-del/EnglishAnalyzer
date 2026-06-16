"""意见反馈 / BUG 报告（§13.3）：功能建议/BUG，文字+截图 → 后台汇总。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import UserFeedback

_KINDS = {"suggestion", "bug"}
_ACTIONS = {"reviewing", "done", "dismissed"}


def _item(f: UserFeedback) -> dict:
    return {
        "id": str(f.id), "user_id": str(f.user_id), "kind": f.kind,
        "content": f.content, "images": f.images or [], "contact": f.contact,
        "status": f.status, "note": f.note,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "handled_at": f.handled_at.isoformat() if f.handled_at else None,
    }


async def submit(db: AsyncSession, *, user_id: uuid.UUID, kind: str, content: str,
                 images: list[str] | None = None, contact: str | None = None) -> UserFeedback:
    if kind not in _KINDS:
        raise AppError(code=400, message="无效反馈类型")
    content = (content or "").strip()
    if not content:
        raise AppError(code=400, message="反馈内容不能为空")
    imgs = [str(u) for u in (images or [])][:6] or None
    f = UserFeedback(
        id=uuid.uuid4(), user_id=user_id, kind=kind, content=content,
        images=imgs, contact=(contact or "").strip() or None, status="pending")
    db.add(f)
    await db.flush()
    return f


async def list_mine(db: AsyncSession, *, user_id: uuid.UUID,
                    skip: int = 0, limit: int = 50) -> dict:
    stmt = select(UserFeedback).where(UserFeedback.user_id == user_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(UserFeedback.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(f) for f in rows]}


async def admin_list(db: AsyncSession, *, status: str = "pending", kind: str = "all",
                     skip: int = 0, limit: int = 50) -> dict:
    stmt = select(UserFeedback)
    if status and status != "all":
        stmt = stmt.where(UserFeedback.status == status)
    if kind and kind != "all":
        stmt = stmt.where(UserFeedback.kind == kind)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(UserFeedback.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(f) for f in rows]}


async def handle(db: AsyncSession, *, feedback_id: uuid.UUID, admin_id: uuid.UUID,
                 action: str, note: str | None) -> UserFeedback:
    if action not in _ACTIONS:
        raise AppError(code=400, message="无效操作")
    f = await db.get(UserFeedback, feedback_id)
    if f is None:
        raise AppError(code=404, message="反馈不存在")
    f.status = action
    f.note = (note or "").strip() or None
    f.handled_by = admin_id
    f.handled_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()
    return f


async def stats(db: AsyncSession) -> dict:
    pending = int(await db.scalar(
        select(func.count()).select_from(UserFeedback).where(
            UserFeedback.status == "pending")) or 0)
    return {"pending": pending}
