"""R7.1 统一接入 ingest_service:ingest_parsed(挂node/落候选/错题收口)+ record_wrong_answer。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d16_question_domain import UploadedQuestion, UploadedQuestionKp, WrongRecord, StudentKp
from app.services.kp_normalize import normalize_kp_name
from app.services import ingest_service as ing

_TAG = "ingsvc"
HIT = f"{_TAG}一般现在时"
MISS = f"{_TAG}独有概念xyz"


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        await db.commit()
    return nid


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM uploaded_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_ingest_parsed():
    node_id = await _seed_node()
    student = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            items = [
                ing.IngestItem(question_no="1", stem="q1", student_answer="A", correct_answer="B",
                               is_wrong=True, kp_name=HIT),     # 命中 + 错题
                ing.IngestItem(question_no="2", stem="q2", student_answer="C", correct_answer="C",
                               is_wrong=False, kp_name=MISS),   # 未命中 + 对题
            ]
            res = await ing.ingest_parsed(db, owner_scope="student", owner_id=student,
                                          items=items, source_type="uploaded_student")
            await db.commit()
            assert len(res) == 2
            assert res[0].node_id == node_id and res[0].wrong_record_id is not None
            assert res[1].node_id is None and res[1].candidate_id is not None and res[1].wrong_record_id is None

        async with _async_session_factory() as db:
            # 2 道 uploaded_question
            uqc = (await db.execute(select(func.count()).select_from(UploadedQuestion)
                   .where(UploadedQuestion.owner_id == student))).scalar_one()
            assert uqc == 2
            # 命中题挂 node
            edge = (await db.execute(select(UploadedQuestionKp.node_id)
                    .where(UploadedQuestionKp.question_id == res[0].question_id))).scalar_one()
            assert edge == node_id
            # 错题进 wrong_record(uploaded)
            wr = (await db.execute(select(WrongRecord).where(WrongRecord.id == res[0].wrong_record_id))).scalar_one()
            assert wr.q_scope == "uploaded" and wr.node_id == node_id and wr.status == "open"
            # student_kp 来源含 wrong_hit
            kp = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == node_id))).scalar_one()
            assert "wrong_hit" in kp.source_tags
            # 未命中 → 候选
            assert (await db.execute(select(KpCandidate).where(KpCandidate.raw_name == MISS))).scalar_one()
    finally:
        await _cleanup(student, node_id)


@pytest.mark.asyncio
async def test_record_wrong_answer():
    node_id = await _seed_node()
    student = uuid.uuid4()
    qid = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            wid = await ing.record_wrong_answer(db, student_id=student, q_scope="platform",
                                                question_id=qid, kp_name=HIT)
            await db.commit()
            assert wid is not None
        async with _async_session_factory() as db:
            wr = (await db.execute(select(WrongRecord).where(WrongRecord.id == wid))).scalar_one()
            assert wr.node_id == node_id and wr.q_scope == "platform" and wr.question_id == qid
    finally:
        await _cleanup(student, node_id)
