"""R7.2 单题拍照错题接入:OCR 管线完成 → uploaded_question + wrong_record(uploaded)(闭 R3 遗留)。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d16_question_domain import UploadedQuestion, WrongRecord
from app.api.v1.ocr import _run_ocr_pipeline

_TAG = "ocring"


async def _cleanup(student):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM ocr_tasks WHERE wrong_question_id IN "
                              "(SELECT id FROM wrong_questions WHERE student_id = :s)"), {"s": str(student)})
        await db.execute(text("DELETE FROM wrong_questions WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM users WHERE id = :s"), {"s": str(student)})
        await db.commit()


@pytest.mark.asyncio
async def test_single_photo_wrong_enters_wrong_record():
    student = uuid.uuid4()
    wq_id = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(User(id=student, openid=f"{_TAG}_{student.hex[:8]}", role="student"))
        db.add(WrongQuestion(id=wq_id, student_id=student,
                             source_image_url="https://cdn.x/wq.jpg", ocr_status="pending"))
        await db.commit()
    try:
        await _run_ocr_pipeline(wq_id)   # dev-mock OCR + classify(backend/tests conftest 强制 dev)

        async with _async_session_factory() as db:
            # 旧 WrongQuestion 仍 completed(不破坏)
            wq = (await db.execute(select(WrongQuestion).where(WrongQuestion.id == wq_id))).scalar_one()
            assert wq.ocr_status == "completed"
            # R7:单题错题进 uploaded_question + wrong_record(uploaded)
            uqc = (await db.execute(select(func.count()).select_from(UploadedQuestion)
                   .where(UploadedQuestion.owner_id == student))).scalar_one()
            assert uqc == 1
            wr = (await db.execute(select(WrongRecord).where(
                WrongRecord.student_id == student, WrongRecord.q_scope == "uploaded"))).scalars().all()
            assert len(wr) == 1 and wr[0].status == "open"
    finally:
        await _cleanup(student)
