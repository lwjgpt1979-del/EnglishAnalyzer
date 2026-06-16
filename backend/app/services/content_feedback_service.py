"""内容质量反馈（§5.5）：用户上报诊断/题目有误 → 后台处理。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import ContentFeedback

_TYPES = {"diagnosis", "question"}


def _item(f: ContentFeedback) -> dict:
    return {
        "id": str(f.id), "target_type": f.target_type, "target_id": f.target_id,
        "snippet": f.snippet, "reason": f.reason, "status": f.status, "note": f.note,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "handled_at": f.handled_at.isoformat() if f.handled_at else None,
    }


async def submit(db: AsyncSession, *, user_id: uuid.UUID, target_type: str,
                 target_id: str | None, snippet: str | None, reason: str | None) -> ContentFeedback:
    if target_type not in _TYPES:
        raise AppError(code=400, message="无效的反馈类型")
    rec = ContentFeedback(
        id=uuid.uuid4(), user_id=user_id, target_type=target_type,
        target_id=(target_id or None), snippet=(snippet or None),
        reason=(reason or None), status="pending")
    db.add(rec)
    await db.flush()
    return rec


async def admin_list(db: AsyncSession, *, status: str = "pending",
                     target_type: str = "all", skip: int = 0, limit: int = 50) -> dict:
    stmt = select(ContentFeedback)
    if status and status != "all":
        stmt = stmt.where(ContentFeedback.status == status)
    if target_type and target_type != "all":
        stmt = stmt.where(ContentFeedback.target_type == target_type)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(ContentFeedback.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(f) for f in rows]}


async def handle(db: AsyncSession, *, feedback_id: uuid.UUID, admin_id: uuid.UUID,
                 action: str, note: str | None) -> ContentFeedback:
    """处理反馈：action=handled(已处理/采纳) | dismissed(忽略/无效)。"""
    if action not in ("handled", "dismissed"):
        raise AppError(code=400, message="无效操作")
    f = await db.get(ContentFeedback, feedback_id)
    if f is None:
        raise AppError(code=404, message="反馈不存在")
    f.status = action
    f.note = (note or "").strip() or None
    f.handled_by = admin_id
    f.handled_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()
    return f


async def stats(db: AsyncSession, *, since: dt.datetime) -> dict:
    """大盘用：周期内反馈数（按类型 + 待处理）。"""
    rows = (await db.execute(
        select(ContentFeedback.target_type, func.count())
        .where(ContentFeedback.created_at >= since)
        .group_by(ContentFeedback.target_type))).all()
    by_type = {str(t): c for t, c in rows}
    pending = int(await db.scalar(
        select(func.count()).select_from(ContentFeedback).where(
            ContentFeedback.status == "pending")) or 0)
    return {"diagnosis": by_type.get("diagnosis", 0),
            "question": by_type.get("question", 0), "pending": pending}
