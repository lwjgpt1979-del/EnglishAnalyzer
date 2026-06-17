"""R3.4 错题复习(KP-First):基于 wrong_record 的 SM-2 复习队列/提交。

复用 review_service.sm2_update 纯算法;数据载体从旧 wrong_questions 切到 wrong_record。
今日队列:status=open AND next_review_at <= today。复习提交按 SM-2 调度;
quality≥4 且 review_count≥3 且 interval≥21 → 判掌握(mastery_source=review)。
"""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d16_question_domain import WrongRecord
from app.services.review_service import sm2_update

_MAX_DAILY_QUEUE = 20
_MASTER_MIN_INTERVAL = 21       # 连续高质量且间隔≥21天 → 判长期掌握


async def get_due_queue(
    db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None,
    limit: int = _MAX_DAILY_QUEUE,
) -> list[WrongRecord]:
    """今日待复习错题:open 且 next_review_at <= today,近期优先。"""
    today = today or _dt.date.today()
    return list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id,
            WrongRecord.status == "open",
            WrongRecord.next_review_at.isnot(None),
            WrongRecord.next_review_at <= today,
        ).order_by(WrongRecord.next_review_at).limit(limit)
    )).scalars().all())


async def submit_review(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    quality: int, today: _dt.date | None = None,
) -> WrongRecord:
    """提交一次复习评分 → SM-2 更新 next_review_at;达标则判掌握。"""
    today = today or _dt.date.today()
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在")

    r = sm2_update(
        quality=quality, review_count=wr.review_count,
        easiness_factor=Decimal(str(wr.easiness_factor)),
        review_interval_days=wr.review_interval_days, today=today,
    )
    wr.review_count = r.review_count
    wr.easiness_factor = r.easiness_factor
    wr.review_interval_days = r.review_interval_days
    wr.next_review_at = r.next_review_at
    wr.last_review_at = today

    if quality >= 4 and r.review_count >= 3 and r.review_interval_days >= _MASTER_MIN_INTERVAL:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "review"
    await db.flush()
    return wr
