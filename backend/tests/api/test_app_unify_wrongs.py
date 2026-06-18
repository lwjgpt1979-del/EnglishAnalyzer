"""R7.3 应用统一-错题收口:听力/作业错题 → wrong_record(record_wrong_answer)。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d16_question_domain import WrongRecord
from app.services import listening_service, assignment_service

_TAG = "appuw"


async def _mk_user() -> uuid.UUID:
    uid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(User(id=uid, openid=f"{_TAG}_{uid.hex[:8]}", role="student"))
        await db.commit()
    return uid


async def _cleanup(uid):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM listening_wrong_questions WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM wrong_questions WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM users WHERE id = :s"), {"s": str(uid)})
        await db.commit()


@pytest.mark.asyncio
async def test_listening_wrong_enters_wrong_record():
    uid = await _mk_user()
    try:
        ex_id = next(iter(listening_service._BY_ID))      # 取一个种子听力素材
        ex = listening_service._BY_ID[ex_id]
        wrong_answers = [-1] * len(ex["questions"])       # 全答错
        async with _async_session_factory() as db:
            await listening_service.submit_answers(db, student_id=uid, exercise_id=ex_id, answers=wrong_answers)
            await db.commit()
        async with _async_session_factory() as db:
            cnt = (await db.execute(select(func.count()).select_from(WrongRecord)
                   .where(WrongRecord.student_id == uid, WrongRecord.q_scope == "platform"))).scalar_one()
            assert cnt == len(ex["questions"]) and cnt >= 1   # 听力错题进 wrong_record
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_assignment_wrong_enters_wrong_record():
    uid = await _mk_user()
    aid = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            await assignment_service._sync_assignment_wrongs(
                db, student_id=uid, assignment_id=aid,
                wrong_items=[{"stem": "q1", "student_answer": "A", "correct_answer": "B", "kp": "一般现在时"}])
            await db.commit()
        async with _async_session_factory() as db:
            cnt = (await db.execute(select(func.count()).select_from(WrongRecord)
                   .where(WrongRecord.student_id == uid, WrongRecord.q_scope == "uploaded"))).scalar_one()
            assert cnt == 1   # 作业错题进 wrong_record
    finally:
        await _cleanup(uid)
