"""R3.2 有源练同类:有真题→派生仿真(带parent)/ 无真题→KP直生备选 / 复用不超量。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services import platform_question_service as pqs
from app.services import wrong_practice_service as wp

_TAG = "wprac"


async def _seed_node(code) -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}{code}",
                             code=f"{_TAG}-{code}", status="active", source="seed"))
        await db.commit()
    return nid


async def _seed_real_on(node_id) -> uuid.UUID:
    rid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(PlatformQuestion(id=rid, type="real", question_type="单选",
                                stem=f"{_TAG} 真题", answer="A", status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=rid, node_id=node_id))
        await db.commit()
    return rid


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id IN "
                              "(SELECT id FROM knowledge_nodes WHERE code LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p OR stem LIKE :q"),
                         {"p": f"{_TAG}%", "q": f"%{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_practice_derives_from_real():
    node_id = await _seed_node("hasreal")
    real_id = await _seed_real_on(node_id)
    try:
        async with _async_session_factory() as db:
            res = await wp.practice_same_kind(db, node_id=node_id, count=3)
            await db.commit()
            assert res.real_id == real_id and res.fallback is False
            assert len(res.sim_ids) == 3
        async with _async_session_factory() as db:
            for sid in res.sim_ids:
                s = (await db.execute(select(PlatformQuestion).where(PlatformQuestion.id == sid))).scalar_one()
                assert s.type == "sim" and s.parent_real_id == real_id and not s.is_fallback
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_practice_fallback_when_no_real():
    node_id = await _seed_node("noreal")
    try:
        async with _async_session_factory() as db:
            res = await wp.practice_same_kind(db, node_id=node_id, count=2)
            await db.commit()
            assert res.real_id is None and res.fallback is True and len(res.sim_ids) == 2
        async with _async_session_factory() as db:
            for sid in res.sim_ids:
                s = (await db.execute(select(PlatformQuestion).where(PlatformQuestion.id == sid))).scalar_one()
                assert s.is_fallback and s.parent_real_id is None
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_practice_reuses_existing_no_overgen():
    node_id = await _seed_node("reuse")
    await _seed_real_on(node_id)
    try:
        async with _async_session_factory() as db:
            await wp.practice_same_kind(db, node_id=node_id, count=3)
            await db.commit()
        async with _async_session_factory() as db:
            await wp.practice_same_kind(db, node_id=node_id, count=3)  # 复跑
            await db.commit()
        async with _async_session_factory() as db:
            cnt = (await db.execute(
                select(func.count()).select_from(PlatformQuestion)
                .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
                .where(PlatformQuestionKp.node_id == node_id, PlatformQuestion.type == "sim")
            )).scalar_one()
            assert cnt == 3   # 复用,不超量生成
    finally:
        await _cleanup()
