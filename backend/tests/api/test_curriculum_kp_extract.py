"""R1.2 教材单元抽取:命中建 unit_node 边 / 未命中落候选(带 unit 来源)/ 幂等。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import normalize_kp_name
from app.services import curriculum_kp_service as svc

_TAG = "ckext"
HIT = f"{_TAG}一般现在时"
MISS = f"{_TAG}独有概念xyz"


async def _seed():
    unit_id, node_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="初中7年级",
                              semester="上", unit_no=1, unit_title=f"{_TAG}U1"))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法",
                             name=HIT, code=f"{_TAG}-n", status="active", source="textbook",
                             applicable_stages=["初"]))
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
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
        await db.commit()


@pytest.mark.asyncio
async def test_extract_hit_edge_and_miss_candidate():
    unit_id, node_id = await _seed()
    try:
        async with _async_session_factory() as db:
            res = await svc.extract_unit_nodes(db, unit_id=unit_id, kp_names=[HIT, MISS])
            await db.commit()
            assert res.stats == {"matched": 1, "candidate": 1, "edges_created": 1}
            assert res.matched[0]["node_id"] == node_id

        async with _async_session_factory() as db:
            # 命中 → unit_node 边
            edge = (await db.execute(
                select(UnitNode).where(UnitNode.unit_id == unit_id, UnitNode.node_id == node_id)
            )).scalar_one()
            assert edge.source == "ai_extract"
            # 未命中 → 候选,且 source_ref.unit_ids 带本单元
            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == MISS)
            )).scalar_one()
            assert cand.suggested_axis == "knowledge" and cand.suggested_stage == "初"
            assert str(unit_id) in (cand.source_ref or {}).get("unit_ids", [])

        # ── 幂等:复跑不重复建边、不重复候选,候选 occur++,unit_ids 不重复 ──
        async with _async_session_factory() as db:
            res2 = await svc.extract_unit_nodes(db, unit_id=unit_id, kp_names=[HIT, MISS])
            await db.commit()
            assert res2.edges_created == 0          # 边已存在
            edge_count = (await db.execute(
                select(func.count()).select_from(UnitNode).where(UnitNode.unit_id == unit_id)
            )).scalar_one()
            assert edge_count == 1
            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == MISS)
            )).scalar_one()
            assert cand.occur_count == 2
            assert (cand.source_ref or {}).get("unit_ids") == [str(unit_id)]  # 去重
    finally:
        await _cleanup(unit_id)
