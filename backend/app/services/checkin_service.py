"""词力通每日打卡（P1 / D-104）。复用 study_checkins，零迁移。

streak 推算：只看"昨天有无打卡行"决定从昨天+1 还是从 1 起（断签自然归零），O(1)。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudyCheckin
from app.services import vocabulary_service


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def _row_for(db: AsyncSession, student_id: uuid.UUID, d: date) -> StudyCheckin | None:
    return (await db.execute(
        select(StudyCheckin).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date == d,
        )
    )).scalar_one_or_none()


async def _upsert_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    new_words_count: int,
    review_done: bool,
) -> StudyCheckin:
    """写入/更新当日打卡行（streak 推算）。同日重复调用幂等（更新计数、streak 不变）。"""
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


async def record_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> tuple[StudyCheckin | None, dict]:
    """严格校验今日任务完成度，达标才写打卡。返回 (打卡行 or None, progress)。"""
    progress = await vocabulary_service.compute_today_progress(db, student_id=student_id)
    if not progress["all_done"]:
        return None, progress
    row = await _upsert_checkin(
        db,
        student_id=student_id,
        new_words_count=progress["new_learned_today"],
        review_done=True,
    )
    return row, progress


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


async def get_month_calendar(
    db: AsyncSession, *, student_id: uuid.UUID, year: int, month: int,
) -> dict:
    """当月打卡日历：已打卡日列表 + 连续/最高天数（复用 status 摘要）。"""
    month_start = date(year, month, 1)
    next_month_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows = (await db.execute(
        select(StudyCheckin).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date >= month_start,
            StudyCheckin.checkin_date < next_month_start,
        ).order_by(StudyCheckin.checkin_date)
    )).scalars().all()
    days = [
        {
            "date": r.checkin_date.isoformat(),
            "new_words_count": r.new_words_count,
            "streak_days": r.streak_days,
        }
        for r in rows
    ]
    status = await get_checkin_status(db, student_id=student_id)
    return {
        "year": year,
        "month": month,
        "days": days,
        "checked_count": len(days),
        "current_streak": status["current_streak"],
        "longest_streak": status["longest_streak"],
    }
