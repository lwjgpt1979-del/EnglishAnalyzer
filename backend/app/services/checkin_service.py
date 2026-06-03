"""词力通每日打卡（P1 / D-104）。复用 study_checkins，零迁移。

streak 推算：只看"昨天有无打卡行"决定从昨天+1 还是从 1 起（断签自然归零），O(1)。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudyCheckin


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def _row_for(db: AsyncSession, student_id: uuid.UUID, d: date) -> StudyCheckin | None:
    return (await db.execute(
        select(StudyCheckin).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date == d,
        )
    )).scalar_one_or_none()


async def record_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    new_words_count: int = 0,
    review_done: bool = False,
) -> StudyCheckin:
    """记录当日打卡。同日重复调用幂等（更新计数、streak 不变）。"""
    today = _today()
    row = await _row_for(db, student_id, today)
    if row is not None:
        row.new_words_count = new_words_count
        row.review_done = review_done
        await db.flush()
        return row
    yesterday = await _row_for(db, student_id, today - timedelta(days=1))
    streak = (yesterday.streak_days + 1) if yesterday is not None else 1
    row = StudyCheckin(
        id=uuid.uuid4(),
        student_id=student_id,
        checkin_date=today,
        new_words_count=new_words_count,
        review_done=review_done,
        streak_days=streak,
    )
    db.add(row)
    await db.flush()
    return row


async def get_checkin_status(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """返回打卡状态：今日是否已打、当前连续、历史最高、今日计数。"""
    today = _today()
    today_row = await _row_for(db, student_id, today)
    yest_row = await _row_for(db, student_id, today - timedelta(days=1))
    if today_row is not None:
        current = today_row.streak_days
    elif yest_row is not None:
        current = yest_row.streak_days  # 今日待打、连续仍保持
    else:
        current = 0
    longest = (await db.execute(
        select(func.coalesce(func.max(StudyCheckin.streak_days), 0))
        .where(StudyCheckin.student_id == student_id)
    )).scalar_one()
    return {
        "checked_in_today": today_row is not None,
        "current_streak": current,
        "longest_streak": int(longest),
        "today_new_words": today_row.new_words_count if today_row else 0,
        "today_review_done": today_row.review_done if today_row else False,
    }
