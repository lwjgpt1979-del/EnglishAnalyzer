"""SM-2 错题智能复习计划服务（V2 M36）。

算法：改进型 SM-2（SuperMemo 2）
  quality: 0-5
    0 = 完全忘记
    3 = 模糊记得（需加强）
    4 = 答对但有些犹豫
    5 = 完全掌握
  < 3: 重新复习（interval=1，review_count 重置）
  >= 3:
    review_count=0 → interval=1
    review_count=1 → interval=6
    else           → interval = round(prev_interval * easiness_factor)
    easiness_factor = max(1.3, ef + 0.1 - (5-q)*(0.08 + (5-q)*0.02))
    review_count += 1

每天今日队列：next_review_at <= today AND is_mastered = false。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d3_wrong_questions import WrongQuestion

_DEFAULT_EASINESS = Decimal("2.50")
_MIN_EASINESS = Decimal("1.30")
_MAX_DAILY_QUEUE = 20          # 每日最多推送题数，防刷题疲劳


# ── SM-2 纯算法（无 DB 依赖，便于单元测试）────────────────────────────────────

@dataclass
class SM2Result:
    review_count: int
    easiness_factor: Decimal
    review_interval_days: int
    next_review_at: date


def sm2_update(
    *,
    quality: int,                   # 0-5
    review_count: int,
    easiness_factor: Decimal,
    review_interval_days: int,
    today: date | None = None,
) -> SM2Result:
    """计算下一次复习参数。quality 必须在 0-5 之间。"""
    if not (0 <= quality <= 5):
        raise ValueError(f"quality must be 0-5, got {quality}")

    today = today or date.today()

    if quality < 3:
        # 质量太低：重置复习轮次，明天再复习
        new_count = 0
        new_interval = 1
        new_ef = easiness_factor  # 遗忘不降低难度系数
    else:
        # 计算新的 easiness_factor
        q = Decimal(str(quality))
        delta = Decimal("0.1") - (Decimal("5") - q) * (
            Decimal("0.08") + (Decimal("5") - q) * Decimal("0.02")
        )
        new_ef = max(_MIN_EASINESS, easiness_factor + delta)

        # 计算新间隔
        if review_count == 0:
            new_interval = 1
        elif review_count == 1:
            new_interval = 6
        else:
            new_interval = max(1, round(float(review_interval_days) * float(new_ef)))

        new_count = review_count + 1

    next_date = today + timedelta(days=new_interval)

    return SM2Result(
        review_count=new_count,
        easiness_factor=new_ef,
        review_interval_days=new_interval,
        next_review_at=next_date,
    )


# ── DB 操作 ───────────────────────────────────────────────────────────────────

async def get_today_review_queue(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    today: date | None = None,
) -> list[WrongQuestion]:
    """返回今日待复习的错题（next_review_at <= today，未掌握）。"""
    today = today or date.today()
    rows = list(
        (await db.execute(
            select(WrongQuestion)
            .where(
                WrongQuestion.student_id == student_id,
                WrongQuestion.is_mastered.is_(False),
                WrongQuestion.next_review_at <= today,
                WrongQuestion.next_review_at.is_not(None),
            )
            .order_by(WrongQuestion.next_review_at.asc())
            .limit(_MAX_DAILY_QUEUE)
        )).scalars().all()
    )
    return rows


async def get_new_queue(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    limit: int = 5,
) -> list[WrongQuestion]:
    """返回从未安排复习（next_review_at IS NULL）的新错题，为其初始化调度。"""
    rows = list(
        (await db.execute(
            select(WrongQuestion)
            .where(
                WrongQuestion.student_id == student_id,
                WrongQuestion.is_mastered.is_(False),
                WrongQuestion.next_review_at.is_(None),
            )
            .order_by(WrongQuestion.created_at.asc())
            .limit(limit)
        )).scalars().all()
    )
    # 新题：今天就安排复习
    today = date.today()
    for wq in rows:
        wq.next_review_at = today
    if rows:
        await db.flush()
    return rows


async def submit_review(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
    student_id: uuid.UUID,
    quality: int,
) -> WrongQuestion:
    """提交一道错题的复习质量，更新 SM-2 调度参数。"""
    wq = (await db.execute(
        select(WrongQuestion).where(
            WrongQuestion.id == wq_id,
            WrongQuestion.student_id == student_id,
        )
    )).scalar_one_or_none()
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    if wq.is_mastered:
        raise AppError(code=400, message="该题已标记为掌握，无需复习")

    today = date.today()
    result = sm2_update(
        quality=quality,
        review_count=int(wq.review_count or 0),
        easiness_factor=Decimal(str(wq.easiness_factor or _DEFAULT_EASINESS)),
        review_interval_days=int(wq.review_interval_days or 1),
        today=today,
    )

    wq.review_count = result.review_count
    wq.easiness_factor = result.easiness_factor
    wq.review_interval_days = result.review_interval_days
    wq.next_review_at = result.next_review_at
    wq.last_review_at = today

    # quality >= 4 且连续多次高分 → 自动标记掌握
    if quality >= 4 and result.review_count >= 3 and result.review_interval_days >= 21:
        wq.is_mastered = True
        from datetime import datetime, timezone
        wq.mastered_at = datetime.now(timezone.utc)

    await db.flush()
    return wq


async def get_review_stats(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> dict:
    """返回复习统计概览。"""
    from sqlalchemy import func
    today = date.today()

    total_unmastered = (await db.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == student_id,
            WrongQuestion.is_mastered.is_(False),
        )
    )).scalar_one()

    due_today = (await db.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == student_id,
            WrongQuestion.is_mastered.is_(False),
            WrongQuestion.next_review_at <= today,
            WrongQuestion.next_review_at.is_not(None),
        )
    )).scalar_one()

    new_unscheduled = (await db.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == student_id,
            WrongQuestion.is_mastered.is_(False),
            WrongQuestion.next_review_at.is_(None),
        )
    )).scalar_one()

    return {
        "total_unmastered": int(total_unmastered),
        "due_today": int(due_today),
        "new_unscheduled": int(new_unscheduled),
    }
