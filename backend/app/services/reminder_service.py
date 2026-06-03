"""打卡提醒编排（D-108）。找出"昨日有/今日无"的学生，双通道发送。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d5_learning import StudyCheckin
from app.services import checkin_service, notification_service, wechat_subscribe_service


async def find_reminder_targets(db: AsyncSession) -> list[tuple[uuid.UUID, str | None]]:
    """昨日有打卡行、今日无打卡行的学生 → [(student_id, openid)]。"""
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    yest_ids = {r[0] for r in (await db.execute(
        select(StudyCheckin.student_id).where(StudyCheckin.checkin_date == yesterday)
    )).all()}
    today_ids = {r[0] for r in (await db.execute(
        select(StudyCheckin.student_id).where(StudyCheckin.checkin_date == today)
    )).all()}
    targets = yest_ids - today_ids
    if not targets:
        return []
    rows = (await db.execute(
        select(User.id, User.openid).where(User.id.in_(targets))
    )).all()
    return [(r[0], r[1]) for r in rows]


async def run_checkin_reminders(db: AsyncSession) -> dict:
    """对所有待提醒学生发送站内 + 微信订阅消息（dev-mock）。返回 {notified}。"""
    targets = await find_reminder_targets(db)
    notified = 0
    for student_id, openid in targets:
        status = await checkin_service.get_checkin_status(db, student_id=student_id)
        await notification_service.emit_checkin_reminder(
            db, user_id=student_id, streak_days=status["current_streak"])
        if openid:
            await wechat_subscribe_service.send_checkin_reminder(
                openid=openid, streak_days=status["current_streak"])
        notified += 1
    return {"notified": notified}
