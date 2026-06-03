"""词力通每日打卡（P1 / D-104）。复用 study_checkins，零迁移。

streak 推算：只看"昨天有无打卡行"决定从昨天+1 还是从 1 起（断签自然归零），O(1)。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
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


def _run_ending_at(dates: set[date], d: date) -> int:
    n = 0
    while d in dates:
        n += 1
        d -= timedelta(days=1)
    return n


def _compute_streaks(dates: set[date], today: date) -> tuple[int, int]:
    """从打卡日期集合算 (current_streak, longest_streak)。"""
    if not dates:
        return 0, 0
    if today in dates:
        anchor = today
    elif (today - timedelta(days=1)) in dates:
        anchor = today - timedelta(days=1)
    else:
        anchor = None
    current = _run_ending_at(dates, anchor) if anchor is not None else 0
    longest = 0
    for d in dates:
        if (d - timedelta(days=1)) not in dates:  # 连续段起点
            run = 0
            x = d
            while x in dates:
                run += 1
                x += timedelta(days=1)
            longest = max(longest, run)
    return current, longest


_BADGE_DEFS = [("bronze", "坚持铜章", 7), ("silver", "毅力银章", 30), ("gold", "登峰金章", 100)]


def _badges(longest_streak: int) -> list[dict]:
    return [{"level": lv, "name": nm, "threshold": th, "unlocked": longest_streak >= th}
            for lv, nm, th in _BADGE_DEFS]


async def _all_dates(db: AsyncSession, student_id: uuid.UUID) -> set[date]:
    rows = (await db.execute(
        select(StudyCheckin.checkin_date).where(StudyCheckin.student_id == student_id)
    )).all()
    return {r[0] for r in rows}


async def _upsert_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    new_words_count: int,
    review_done: bool,
    checkin_date: date | None = None,
) -> StudyCheckin:
    """写入/更新某日打卡行；streak_days = 以该日结尾的连续段长度（动态）。"""
    d = checkin_date or _today()
    dates = await _all_dates(db, student_id)
    dates.add(d)
    run = _run_ending_at(dates, d)
    row = await _row_for(db, student_id, d)
    if row is not None:
        row.new_words_count = new_words_count
        row.review_done = review_done
        row.streak_days = run
        await db.flush()
        return row
    row = StudyCheckin(
        id=uuid.uuid4(),
        student_id=student_id,
        checkin_date=d,
        new_words_count=new_words_count,
        review_done=review_done,
        streak_days=run,
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
    """返回打卡状态：今日是否已打、当前连续、历史最高、今日计数（按日期集合动态算）。"""
    today = _today()
    rows = (await db.execute(
        select(StudyCheckin.checkin_date, StudyCheckin.new_words_count, StudyCheckin.review_done)
        .where(StudyCheckin.student_id == student_id)
    )).all()
    dates = {r[0] for r in rows}
    current, longest = _compute_streaks(dates, today)
    today_row = next((r for r in rows if r[0] == today), None)
    return {
        "checked_in_today": today in dates,
        "current_streak": current,
        "longest_streak": longest,
        "today_new_words": today_row[1] if today_row else 0,
        "today_review_done": today_row[2] if today_row else False,
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


async def make_up_checkin(db: AsyncSession, *, student_id: uuid.UUID, d: date) -> dict:
    """补签某漏签日（当月内、早于今天、未打卡）。恢复连续。返回 {date, current_streak, longest_streak}。"""
    today = _today()
    if d >= today:
        raise AppError(code=400, message="只能补签今天之前的日期")
    if d < today.replace(day=1):
        raise AppError(code=400, message="只能补签本月内的日期")
    if await _row_for(db, student_id, d) is not None:
        raise AppError(code=400, message="该日已打卡")
    await _upsert_checkin(db, student_id=student_id, new_words_count=0,
                          review_done=False, checkin_date=d)
    status = await get_checkin_status(db, student_id=student_id)
    return {
        "date": d.isoformat(),
        "current_streak": status["current_streak"],
        "longest_streak": status["longest_streak"],
    }
