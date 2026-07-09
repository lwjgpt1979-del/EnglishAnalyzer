"""R3.4 错题复习(wrong_record + SM-2,客观重做判分):今日队列 / 重做订正 / 复习达标 / 答错重置。

KP-First:submit_review/redo 改为**客观判分**(拿学生作答比对底层平台题答案),不再主观自评。
故每条 wrong_record 需挂一道真实 platform_question(含答案+选项)。
"""
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
_ANSWER = "B"
_OPTS = '["A. 定语", "B. 表语"]'   # jsonb 数组 → coarse 判为单选


async def _seed_record(student, *, review_count=0, interval=1, next_due=None) -> uuid.UUID:
    """建一道 platform_question(答案 B/单选)+ 指向它的 open wrong_record。"""
    rid = uuid.uuid4()
    qid = uuid.uuid4()
    async with _async_session_factory() as db:
        await db.execute(text(
            "INSERT INTO platform_question (id, type, is_fallback, question_type, stem, options, answer, status) "
            "VALUES (:id, 'sim', true, '单选', :stem, CAST(:opts AS jsonb), :ans, 'published')"
        ), {"id": qid, "stem": f"{_TAG} stem", "opts": _OPTS, "ans": _ANSWER})
        db.add(WrongRecord(
            id=rid, student_id=student, q_scope="platform", question_id=qid,
            status="open", review_count=review_count, review_interval_days=interval,
            easiness_factor=Decimal("2.50"), next_review_at=next_due or _dt.date.today(),
        ))
        await db.commit()
    return rid


async def _get(rid) -> WrongRecord:
    async with _async_session_factory() as db:
        return (await db.execute(select(WrongRecord).where(WrongRecord.id == rid))).scalar_one()


async def _cleanup(student):
    async with _async_session_factory() as db:
        await db.execute(text(
            "DELETE FROM platform_question WHERE id IN "
            "(SELECT question_id FROM wrong_record WHERE student_id = :s)"), {"s": str(student)})
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(student)})
        await db.commit()


@pytest.mark.asyncio
async def test_due_queue_and_submit():
    student = uuid.uuid4()
    rid = await _seed_record(student)
    try:
        async with _async_session_factory() as db:
            due = await wr.get_due_queue(db, student_id=student)
            assert any(r.id == rid for r in due)
            # 答对 → quality5 推进 SM-2
            res = await wr.submit_review(db, student_id=student, wrong_record_id=rid, user_answer=_ANSWER)
            await db.commit()
            assert res["is_correct"] is True
        r = await _get(rid)
        assert r.review_count == 1 and r.status == "open"
        assert r.next_review_at > _dt.date.today()   # 已排到将来
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_master_after_threshold():
    student = uuid.uuid4()
    # 已复习 3 次、间隔 20 天 → 再来一次答对 → 间隔≥21、count≥3 → 判掌握
    rid = await _seed_record(student, review_count=3, interval=20)
    try:
        async with _async_session_factory() as db:
            res = await wr.submit_review(db, student_id=student, wrong_record_id=rid, user_answer=_ANSWER)
            await db.commit()
            assert res["mastered"] is True
        r = await _get(rid)
        assert r.status == "mastered" and r.mastery_source == "review"
        assert r.mastered_at is not None
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_wrong_answer_resets():
    student = uuid.uuid4()
    rid = await _seed_record(student, review_count=2, interval=6)
    try:
        async with _async_session_factory() as db:
            # 答错 → quality2(<3)→ SM-2 归零
            res = await wr.submit_review(db, student_id=student, wrong_record_id=rid, user_answer="X")
            await db.commit()
            assert res["is_correct"] is False
        r = await _get(rid)
        assert r.review_count == 0 and r.review_interval_days == 1 and r.status == "open"
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_redo_correct_masters_immediately():
    """错题详情主动重做:答对 → 立即订正(mastered, source=redo),无需多次复习。"""
    student = uuid.uuid4()
    rid = await _seed_record(student)
    try:
        async with _async_session_factory() as db:
            res = await wr.redo(db, student_id=student, wrong_record_id=rid, user_answer=_ANSWER)
            await db.commit()
            assert res["is_correct"] is True and res["mastered"] is True
        r = await _get(rid)
        assert r.status == "mastered" and r.mastery_source == "redo"
    finally:
        await _cleanup(student)


@pytest.mark.asyncio
async def test_redo_wrong_keeps_open_and_reschedules():
    """主动重做答错 → 保持 open、SM-2 归零、今日重排。"""
    student = uuid.uuid4()
    rid = await _seed_record(student, review_count=2, interval=6)
    try:
        async with _async_session_factory() as db:
            res = await wr.redo(db, student_id=student, wrong_record_id=rid, user_answer="X")
            await db.commit()
            assert res["is_correct"] is False and res["mastered"] is False
        r = await _get(rid)
        assert r.status == "open" and r.review_count == 0
        assert r.next_review_at == _dt.date.today()
    finally:
        await _cleanup(student)
