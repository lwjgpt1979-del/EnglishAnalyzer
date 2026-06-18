"""R7 收尾:自助出卷取材切 platform_question——有源题物化进 SimulatedQuestion(判分链复用),去重。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name
from app.services import adaptive_question_service as aqs

_TAG = "apsrc"
HIT = f"{_TAG}一般现在时"


async def _seed():
    kp_id, node_id, pq_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgePoint(id=kp_id, code=f"{_TAG}-kp", name=HIT, category="grammar",
                              applicable_grades=["初中7年级"], applicable_textbooks=[f"{_TAG}版"]))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        db.add(PlatformQuestion(id=pq_id, type="sim", is_fallback=True, question_type="单选",
                                stem=f"{_TAG} She ___ to school.", options=["go", "goes", "going", "gone"],
                                answer="B", explanation="第三人称单数", difficulty=2, status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=pq_id, node_id=node_id))
        await db.commit()
    return kp_id, node_id, pq_id


async def _cleanup(node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM simulated_questions WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_points WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_adaptive_materializes_platform_sim():
    kp_id, node_id, pq_id = await _seed()
    try:
        async with _async_session_factory() as db:
            kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one()
            n = await aqs._materialize_sims_from_platform(db, kp=kp)
            await db.commit()
            assert n == 1
        async with _async_session_factory() as db:
            sq = (await db.execute(select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp_id))).scalar_one()
            assert sq.status == "published" and sq.answer == "B"
            assert sq.generation_metadata["source_platform_question_id"] == str(pq_id)
        # 去重:复跑不新增
        async with _async_session_factory() as db:
            kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one()
            n2 = await aqs._materialize_sims_from_platform(db, kp=kp)
            await db.commit()
            assert n2 == 0
            cnt = (await db.execute(select(func.count()).select_from(SimulatedQuestion)
                   .where(SimulatedQuestion.knowledge_point_id == kp_id))).scalar_one()
            assert cnt == 1
    finally:
        await _cleanup(node_id)
