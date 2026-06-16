"""消息通知服务（Module 7B / D-074）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import Notification

TYPE_TO_CHANNEL = {
    "analysis_done": "study",
    "ocr_failed": "study",
    "report_ready": "study",
    "assignment": "study",
    "membership": "membership",
    "system": "system",
    "bind_request": "relative",
    "bind_accepted": "relative",
    "bind_rejected": "relative",
    "checkin_reminder": "study",
    "weekly_report": "study",
}

RETENTION_DAYS_MEMBERSHIP = 365
RETENTION_DAYS_OTHER = 90


def _channel_for(type_: str) -> str:
    return TYPE_TO_CHANNEL.get(type_, "system")


def _expires_at_for(type_: str) -> datetime:
    days = RETENTION_DAYS_MEMBERSHIP if type_ == "membership" else RETENTION_DAYS_OTHER
    return datetime.now(timezone.utc) + timedelta(days=days)


async def emit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> Notification:
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=type_,
        channel=_channel_for(type_),
        title=title,
        content=content,
        meta=meta,
        expires_at=_expires_at_for(type_),
    )
    db.add(notif)
    await db.flush()
    return notif


async def emit_analysis_done(
    db: AsyncSession, *, user_id: uuid.UUID, wq_id: uuid.UUID,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="analysis_done",
        title="AI 分析完成", content="你的错题已生成诊断报告，点击查看。",
        meta={"wq_id": str(wq_id)},
    )


async def emit_teacher_comment(
    db: AsyncSession, *, user_id: uuid.UUID, wq_id: uuid.UUID, teacher_id: uuid.UUID,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="assignment",
        title="老师为你批注了一道错题", content="点击查看老师的反馈。",
        meta={"wq_id": str(wq_id), "teacher_id": str(teacher_id)},
    )


async def emit_membership(
    db: AsyncSession, *, user_id: uuid.UUID, title: str, content: str,
    order_id: uuid.UUID | None = None,
) -> Notification:
    meta: dict[str, Any] | None = {"order_id": str(order_id)} if order_id else None
    return await emit(
        db, user_id=user_id, type_="membership",
        title=title, content=content, meta=meta,
    )


async def emit_checkin_reminder(
    db: AsyncSession, *, user_id: uuid.UUID, streak_days: int,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="checkin_reminder",
        title="别让连续中断啦",
        content=f"你已连续打卡 {streak_days} 天，今天还没学，快来词力通保持记录！",
        meta={"streak_days": streak_days},
    )


async def list_notifications(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    channel: str | None = None,
    unread_only: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Notification], int, int]:
    base = select(Notification).where(Notification.user_id == user_id)
    if channel:
        base = base.where(Notification.channel == channel)
    if unread_only:
        base = base.where(Notification.is_read.is_(False))

    total_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_q)).scalar_one()

    unread_q = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False),
    )
    unread_count_val = (await db.execute(unread_q)).scalar_one()

    items_q = base.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    items = list((await db.execute(items_q)).scalars().all())
    return items, total, unread_count_val


async def unread_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    q = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False),
    )
    return (await db.execute(q)).scalar_one()


async def unread_by_channel(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """未读数按频道分组（消息中心角标）。返回 {total, by_channel:{channel:n}}。"""
    rows = (await db.execute(
        select(Notification.channel, func.count())
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .group_by(Notification.channel))).all()
    by = {str(c): int(n) for c, n in rows}
    return {"total": sum(by.values()), "by_channel": by}


async def mark_read(db: AsyncSession, *, user_id: uuid.UUID, notif_id: uuid.UUID) -> Notification:
    from app.core.exceptions import AppError
    r = await db.execute(
        select(Notification).where(
            Notification.id == notif_id, Notification.user_id == user_id,
        )
    )
    n = r.scalar_one_or_none()
    if n is None:
        raise AppError(code=404, message="消息不存在")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        await db.flush()
    return n


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    r = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False),
        )
    )
    affected = 0
    for n in r.scalars().all():
        n.is_read = True
        n.read_at = now
        affected += 1
    await db.flush()
    return affected


async def delete_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    r = await db.execute(
        delete(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(True),
        )
    )
    await db.flush()
    return r.rowcount or 0
