"""R7 收尾:练习取材切 platform_question——有源题(已发布有内容仿真)优先物化,去重;无则 AI 兜底。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d6_ai_questions import AiQuestion
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name
from app.services import practice_service as ps

_TAG = "ppsrc"
HIT = f"{_TAG}一般现在时"
MISS = f"{_TAG}无节点知识点"


async def _seed_platform_sim() -> tuple[uuid.UUID, uuid.UUID]:
    node_id, pq_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        db.add(PlatformQuestion(id=pq_id, type="sim", is_fallback=True, question_type="单选",
                                stem=f"{_TAG} She ___ to school.", options=["go", "goes", "going", "gone"],
                                answer="B", explanation="第三人称单数", difficulty=3, status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=pq_id, node_id=node_id))
        await db.commit()
    return node_id, pq_id


async def _purge(db):
    # R8 KP-First:旧 knowledge_points 表 + ai_questions.knowledge_point_id 列已退役,
    # 只按 platform_question 派生的 ai_questions 及新图谱表清理。
    await db.execute(text("DELETE FROM ai_questions WHERE content->>'source_platform_question_id' IN "
                          "(SELECT id::text FROM platform_question WHERE stem LIKE :p)"), {"p": f"{_TAG}%"})
    await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
    await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
    await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})


async def _cleanup(node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await _purge(db)
        await db.commit()


@pytest.mark.asyncio
async def test_practice_sources_from_platform_when_available():
    node_id, pq_id = await _seed_platform_sim()
    student = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            qs = await ps.generate_practice_questions(
                db, student_id=student, knowledge_point=HIT, count=3, difficulty=3)
            await db.commit()
            assert len(qs) == 1   # 该 node 仅 1 道有内容仿真
            assert qs[0].content["source_platform_question_id"] == str(pq_id)
            assert qs[0].content["answer"] == "B" and qs[0].content["options"][1] == "goes"

        # 复跑去重:不新增 AiQuestion(复用同源)
        async with _async_session_factory() as db:
            qs2 = await ps.generate_practice_questions(
                db, student_id=student, knowledge_point=HIT, count=3, difficulty=3)
            await db.commit()
            cnt = (await db.execute(select(func.count()).select_from(AiQuestion)
                   .where(AiQuestion.content["source_platform_question_id"].astext == str(pq_id)))).scalar_one()
            assert cnt == 1
    finally:
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_practice_falls_back_to_ai_when_no_platform():
    """KP 无对应 node/有源题 → 回退 AI 生成(dev mock),练习不空。"""
    student = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            qs = await ps.generate_practice_questions(
                db, student_id=student, knowledge_point=MISS, count=2, difficulty=3)
            await db.commit()
            assert len(qs) >= 1   # AI 兜底
            assert all("source_platform_question_id" not in (q.content or {}) for q in qs)
    finally:
        async with _async_session_factory() as db:
            await _purge(db)
            await db.commit()
