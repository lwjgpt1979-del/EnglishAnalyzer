"""R1 验收闭环:单元抽取 → 命中挂边/未命中候选(带 unit 来源) → 审核 approve → 边自动回填。

把 R1 故事串成一条:教材单元的 2 个知识点名,1 个命中已有节点直接挂边,1 个未命中落候选;
超管 approve 该候选后,单元自动获得第 2 条 unit_node 边 —— 教材完整接入知识图谱。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import normalize_kp_name
from app.services import curriculum_kp_service as ck
from app.services import kp_candidate_service as review

_TAG = "r1acc"
HIT = f"{_TAG}一般现在时"      # 已有节点 → 抽取即挂边
MISS = f"{_TAG}虚拟语气"        # 无节点 → 候选 → 审核后回填


async def _seed_unit_and_node():
    unit_id, node_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="高中1年级",
                              semester="上", unit_no=1, unit_title=f"{_TAG}U1"))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-hit", status="active", source="textbook",
                             applicable_stages=["高"]))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        await db.commit()
    return unit_id, node_id


async def _cleanup(unit_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
        await db.commit()


@pytest.mark.asyncio
async def test_r1_textbook_into_kg_loop():
    unit_id, hit_node = await _seed_unit_and_node()
    try:
        # ── 抽取:HIT 挂边、MISS 落候选(带 unit 来源)──
        async with _async_session_factory() as db:
            res = await ck.extract_unit_nodes(db, unit_id=unit_id, kp_names=[HIT, MISS])
            await db.commit()
            assert res.stats == {"matched": 1, "candidate": 1, "edges_created": 1}
            cand_id = (await db.execute(
                select(KpCandidate.id).where(KpCandidate.raw_name == MISS)
            )).scalar_one()

        # ── 审核 approve MISS → 建节点 + 自动回填单元边 ──
        async with _async_session_factory() as db:
            node = await review.approve(db, candidate_id=cand_id, axis="knowledge",
                                        stage="高", node_kind="句法", reviewer_id=uuid.uuid4())
            await db.commit()
            approved_node = node.id

        # ── 断言:单元现挂 2 个节点(HIT 直接 + MISS 审后回填)──
        async with _async_session_factory() as db:
            nodes = set((await db.execute(
                select(UnitNode.node_id).where(UnitNode.unit_id == unit_id)
            )).scalars().all())
            assert nodes == {hit_node, approved_node}
            cnt = (await db.execute(
                select(func.count()).select_from(UnitNode).where(UnitNode.unit_id == unit_id)
            )).scalar_one()
            assert cnt == 2
    finally:
        await _cleanup(unit_id)
