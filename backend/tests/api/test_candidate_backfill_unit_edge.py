"""R1.3 候选审核回填单元边:approve/merge 后,候选来源单元自动获得 unit_node 边。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import normalize_kp_name
from app.services import kp_candidate_service as review

_TAG = "ckbf"


async def _seed_unit() -> uuid.UUID:
    uid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=uid, textbook_version=f"{_TAG}版", grade="初中7年级",
                              semester="上", unit_no=1, unit_title=f"{_TAG}U1"))
        await db.commit()
    return uid


async def _seed_candidate(name: str, unit_id: uuid.UUID) -> uuid.UUID:
    cid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KpCandidate(id=cid, raw_name=name, name_norm=normalize_kp_name(name),
                           suggested_axis="knowledge", suggested_stage="初", occur_count=1,
                           source_type="textbook", source_ref={"unit_ids": [str(unit_id)]},
                           status="pending"))
        await db.commit()
    return cid


async def _cleanup(unit_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"kp-{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
        await db.commit()


@pytest.mark.asyncio
async def test_approve_backfills_unit_edge():
    unit_id = await _seed_unit()
    cid = await _seed_candidate(f"{_TAG}过去完成时", unit_id)
    try:
        async with _async_session_factory() as db:
            node = await review.approve(db, candidate_id=cid, axis="knowledge", stage="初",
                                        node_kind="句法", reviewer_id=uuid.uuid4())
            await db.commit()
            edge = (await db.execute(
                select(UnitNode).where(UnitNode.unit_id == unit_id, UnitNode.node_id == node.id)
            )).scalar_one()
            assert edge.source == "manual"
    finally:
        await _cleanup(unit_id)


@pytest.mark.asyncio
async def test_merge_backfills_unit_edge():
    unit_id = await _seed_unit()
    target_id = uuid.uuid4()
    target_name = f"{_TAG}过去完成时"
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=target_id, axis="knowledge", node_kind="句法", name=target_name,
                             code=f"{_TAG}-tgt", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=target_id, alias=target_name,
                         alias_norm=normalize_kp_name(target_name), source="seed"))
        await db.commit()
    cid = await _seed_candidate(f"{_TAG}过去完成时态", unit_id)   # 异写,归并入 target
    try:
        async with _async_session_factory() as db:
            await review.merge(db, candidate_id=cid, target_node_id=target_id, reviewer_id=uuid.uuid4())
            await db.commit()
            edge = (await db.execute(
                select(UnitNode).where(UnitNode.unit_id == unit_id, UnitNode.node_id == target_id)
            )).scalar_one()
            assert edge.source == "manual"
    finally:
        await _cleanup(unit_id)
