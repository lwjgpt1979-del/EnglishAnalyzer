"""R3.4 错题复习(wrong_record + SM-2):今日队列 / 提交调度 / 达标判掌握 / 低分重置。"""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d16_question_domain import WrongRecord
from app.services import wrong_review_service as wr

_TAG = "wrev"


async def _seed_record(student, *, review_count=0, interval=1, next_due=None) -> uuid.UUID:
    rid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(WrongRecord(
            id=rid, student_id=student, q_scope="platform", question_id=uuid.uuid4(),
            status="open", review_count=review_count, review_interval_days=interval,
            easiness_factor=Decimal("2.50"), next_review_at=next_due or _dt.date.today(),
        ))
        await db.commit()
    return rid


async def _cleanup(student):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.commit()


@pytest.mark.asyncio
async def test_due_queue_and_submit():
    student = uuid.uuid4()
    rid = await _seed_record(student)
    try:
        async with _async_session_factory() as db:
            due = await wr.get_due_queue(db, student_id=student)
            assert any(r.id == rid for r in due)
            r = await wr.submit_review(db, student_id=student, wrong_record_id=rid, quality=5)
            await db.commit()
            assert r.review_count == 1 and r.status == "open"
            assert r.next_review_at > _dt.date.today()   # 已排到将来
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_master_after_threshold():
    student = uuid.uuid4()
    # 已复习 3 次、间隔 20 天 → 再来一次高质量 → 间隔≥21、count≥3 → 判掌握
    rid = await _seed_record(student, review_count=3, interval=20)
    try:
        async with _async_session_factory() as db:
            r = await wr.submit_review(db, student_id=student, wrong_record_id=rid, quality=5)
            await db.commit()
            assert r.status == "mastered" and r.mastery_source == "review"
            assert r.mastered_at is not None
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_low_quality_resets():
    student = uuid.uuid4()
    rid = await _seed_record(student, review_count=2, interval=6)
    try:
        async with _async_session_factory() as db:
            r = await wr.submit_review(db, student_id=student, wrong_record_id=rid, quality=1)
            await db.commit()
            assert r.review_count == 0 and r.review_interval_days == 1 and r.status == "open"
    finally:
        await _cleanup(student)
