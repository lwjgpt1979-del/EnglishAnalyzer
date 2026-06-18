"""R7.4 口语错题复习读 wrong_record 中心(join uploaded_question 取内容)。"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy import text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import UploadedQuestion, WrongRecord
from app.services import speaking_dialogue_service as sds

_TAG = "spkwc"


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_top_due_wrong_from_center():
    student = uuid.uuid4()
    node_id, uq_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}定从",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(UploadedQuestion(id=uq_id, owner_scope="student", owner_id=student,
                                question_no="3", stem="The book ___ I read.", student_answer="who",
                                correct_answer="which", is_wrong=True))
        await db.flush()
        db.add(WrongRecord(id=uuid.uuid4(), student_id=student, q_scope="uploaded",
                           question_id=uq_id, node_id=node_id, status="open",
                           next_review_at=_dt.date.today()))
        await db.commit()
    try:
        async with _async_session_factory() as db:
            top = await sds._top_due_wrong(db, student)
            assert top is not None
            assert top["stem"].startswith("The book") and top["answer"] == "which"
            assert top["kps"] == [f"{_TAG}定从"]   # 含 node 知识点名
    finally:
        await _cleanup(student, node_id)
