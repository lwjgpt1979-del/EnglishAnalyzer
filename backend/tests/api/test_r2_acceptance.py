"""R2 验收闭环:仿真必有源(派生真题/显式备选)+ 直生备选随真题到来下架。

串起 R2 铁律全链路:
  node B 无真题 → 建 KP 直生备选(is_fallback);
  node A 真题导入 → 预生成派生仿真(parent_real_id + 继承母题 KP);
  node B 真题到来 → B 的备选自动下架;
  全程:每道 type='sim' 都有源(parent 或 fallback),无无源仿真。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name
from app.services import platform_question_service as pq

_TAG = "r2acc"
A = f"{_TAG}定语从句"
B = f"{_TAG}虚拟语气"


async def _seed_node(name, code):
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=name,
                             code=code, status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=name,
                         alias_norm=normalize_kp_name(name), source="seed"))
        await db.commit()
    return nid


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE question_id IN "
                              "(SELECT id FROM platform_question WHERE stem LIKE :p OR stem LIKE :q)"),
                         {"p": f"{_TAG}%", "q": "[备选] " + f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p OR stem LIKE :q"),
                         {"p": f"{_TAG}%", "q": "%" + f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_r2_ironlaw_loop():
    node_a = await _seed_node(A, f"{_TAG}-a")
    node_b = await _seed_node(B, f"{_TAG}-b")
    try:
        # B 无真题 → 建 2 道直生备选
        async with _async_session_factory() as db:
            fbs = await pq.generate_fallback_sim(db, node_id=node_b, count=2)
            await db.commit()
            assert len(fbs) == 2

        # A 真题导入 → 预生成 2 道派生仿真(parent + 继承 A)
        async with _async_session_factory() as db:
            real = await pq.import_real_question(db, stem=f"{_TAG} A真题", answer="A",
                                                 question_type="单选", kp_names=[A])
            await db.commit()
            real_a = real.question_id
        async with _async_session_factory() as db:
            sims_a = await pq.generate_sim_from_real(db, real_id=real_a, count=2)
            await db.commit()
            assert len(sims_a) == 2

        # B 真题到来 → B 的备选自动下架
        async with _async_session_factory() as db:
            await pq.import_real_question(db, stem=f"{_TAG} B真题", answer="B",
                                          question_type="单选", kp_names=[B])
            await db.commit()

        async with _async_session_factory() as db:
            # 派生仿真:带 parent + 继承 A 节点
            for sid in sims_a:
                s = (await db.execute(select(PlatformQuestion).where(PlatformQuestion.id == sid))).scalar_one()
                assert s.parent_real_id == real_a and not s.is_fallback
                nodes = (await db.execute(
                    select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == sid)
                )).scalars().all()
                assert set(nodes) == {node_a}
            # B 的备选已下架
            for fid in fbs:
                f = (await db.execute(select(PlatformQuestion).where(PlatformQuestion.id == fid))).scalar_one()
                assert f.deprecated_at is not None

            # 铁律:本测试所有 type='sim' 都有源(parent 或 fallback)
            sims = (await db.execute(
                select(PlatformQuestion).where(PlatformQuestion.type == "sim",
                                               PlatformQuestion.stem.like(f"%{_TAG}%"))
            )).scalars().all()
            assert sims and all(s.parent_real_id is not None or s.is_fallback for s in sims)
    finally:
        await _cleanup()
