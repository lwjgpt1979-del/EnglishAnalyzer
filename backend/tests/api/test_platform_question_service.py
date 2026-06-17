"""R2.1 平台题写入:仿真铁律(应用层+DB CHECK)/ 真题导入挂 node / 备选下架。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name
from app.services import platform_question_service as pq

_TAG = "pqsvc"
HIT = f"{_TAG}一般现在时"
MISS = f"{_TAG}独有概念xyz"


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-n", status="active", source="textbook"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        await db.commit()
    return nid


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id IN "
                              "(SELECT id FROM knowledge_nodes WHERE code LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_sim_must_have_source_db_check():
    """DB CHECK 兜底:无源仿真(parent 空 + 非 fallback)直接被拒。"""
    try:
        async with _async_session_factory() as db:
            db.add(PlatformQuestion(id=uuid.uuid4(), type="sim", parent_real_id=None,
                                    is_fallback=False, stem=f"{_TAG} 无源仿真", status="draft"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_add_sim_app_guard_and_valid():
    try:
        async with _async_session_factory() as db:
            # 应用层先于 DB 拒绝无源
            with pytest.raises(AppError):
                await pq.add_sim(db, stem=f"{_TAG} x")
            await db.rollback()
        async with _async_session_factory() as db:
            # 显式备选合法
            q = await pq.add_sim(db, stem=f"{_TAG} 备选", is_fallback=True)
            await db.commit()
            assert q.type == "sim" and q.is_fallback is True
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_import_real_attaches_node_and_candidate():
    node_id = await _seed_node()
    try:
        async with _async_session_factory() as db:
            res = await pq.import_real_question(
                db, stem=f"{_TAG} 真题D篇", answer="A", question_type="阅读",
                kp_names=[HIT, MISS], status="published",
            )
            await db.commit()
            assert res.matched_nodes == [node_id]
            assert len(res.candidates) == 1

        async with _async_session_factory() as db:
            real = (await db.execute(
                select(PlatformQuestion).where(PlatformQuestion.id == res.question_id)
            )).scalar_one()
            assert real.type == "real"
            edge = (await db.execute(
                select(PlatformQuestionKp).where(PlatformQuestionKp.question_id == res.question_id)
            )).scalars().all()
            assert {e.node_id for e in edge} == {node_id}
            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == MISS)
            )).scalar_one()
            assert cand.source_type == "exam"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_generate_sim_from_real_inherits_kp_and_parent():
    node_id = await _seed_node()
    try:
        async with _async_session_factory() as db:
            real = await pq.import_real_question(db, stem=f"{_TAG} 真题母题", answer="B",
                                                 question_type="单选", kp_names=[HIT])
            await db.commit()
            real_id = real.question_id

        async with _async_session_factory() as db:
            sim_ids = await pq.generate_sim_from_real(db, real_id=real_id, count=2)
            await db.commit()
            assert len(sim_ids) == 2

        async with _async_session_factory() as db:
            for sid in sim_ids:
                sim = (await db.execute(
                    select(PlatformQuestion).where(PlatformQuestion.id == sid)
                )).scalar_one()
                assert sim.type == "sim" and sim.parent_real_id == real_id and sim.is_fallback is False
                # 继承母题 KP
                edges = (await db.execute(
                    select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == sid)
                )).scalars().all()
                assert set(edges) == {node_id}
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_deprecate_fallbacks_when_real_arrives():
    node_id = await _seed_node()
    try:
        # 该 node 先有一个 KP 直生备选
        async with _async_session_factory() as db:
            fb = await pq.add_sim(db, stem=f"{_TAG} 备选题", is_fallback=True, status="published")
            await pq.attach_node(db, fb.id, node_id)
            await db.commit()
            fb_id = fb.id
        # 真题导入命中该 node → 备选自动下架
        async with _async_session_factory() as db:
            await pq.import_real_question(db, stem=f"{_TAG} 真题", kp_names=[HIT])
            await db.commit()
        async with _async_session_factory() as db:
            fb = (await db.execute(
                select(PlatformQuestion).where(PlatformQuestion.id == fb_id)
            )).scalar_one()
            assert fb.deprecated_at is not None and fb.status == "retired"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_fallback_loop_decision_4():
    """决策④闭环:无真题 node → 建直生备选;真题到来 → 备选下架 + 不再产备选。"""
    node_id = await _seed_node()
    try:
        # 1) 无真题 → 建 2 道 fallback 备选
        async with _async_session_factory() as db:
            fbs = await pq.generate_fallback_sim(db, node_id=node_id, count=2)
            await db.commit()
            assert len(fbs) == 2
        async with _async_session_factory() as db:
            rows = (await db.execute(
                select(PlatformQuestion).where(PlatformQuestion.id.in_(fbs))
            )).scalars().all()
            assert all(r.is_fallback and r.type == "sim" and r.parent_real_id is None for r in rows)

        # 2) 真题到来 → 备选自动下架,且此后 generate_fallback_sim 返回空(已有真题)
        async with _async_session_factory() as db:
            await pq.import_real_question(db, stem=f"{_TAG} 真题到来", kp_names=[HIT])
            await db.commit()
        async with _async_session_factory() as db:
            rows = (await db.execute(
                select(PlatformQuestion).where(PlatformQuestion.id.in_(fbs))
            )).scalars().all()
            assert all(r.deprecated_at is not None for r in rows)
            more = await pq.generate_fallback_sim(db, node_id=node_id, count=2)
            assert more == []   # 已有真题 → 不再产直生备选
    finally:
        await _cleanup()
