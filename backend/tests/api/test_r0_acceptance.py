"""R0 验收闭环(§7):受控匹配 → 候选 → 审核(approve/merge) → 复跑命中、不产生游离点。

把 §7 的核心故事串成一条端到端流程,作为 R0 对齐机制的"总验收":
  Round1  传 3 个知识点名 → 全未命中 → 各落候选(occur_count 聚合)
  审核    approve 其一(建节点+别名) / merge 其二(并入该节点别名,治碎片化)
  Round2  复跑同 3 个名 → 已审的两个命中**同一节点**;未审的仍只累加候选
  断言    knowledge_nodes 仅净增 1(approve 的);全程零游离 auto_ 节点
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, KpCandidate
from app.services import kp_match_service as match
from app.services import kp_candidate_service as review

_TAG = "qacc"
NAME_APPROVE = f"{_TAG}过去完成时"      # 将被 approve 成正式节点
NAME_MERGE = f"{_TAG}过完时"            # 同义异写:不含/不近,只能靠 merge 归一
NAME_MISS = f"{_TAG}宾语前置"           # 始终无人审 → 持续只累加候选
ALL = [NAME_APPROVE, NAME_MERGE, NAME_MISS]


async def _node_count(db) -> int:
    return (await db.execute(select(func.count()).select_from(KnowledgeNode))).scalar_one()


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"kp-{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_r0_alignment_loop():
    reviewer = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            nodes_before = await _node_count(db)

            # ── Round 1:全未命中 → 落候选 ──
            r1 = await match.match_names(db, ALL, source_type="exam")
            await db.commit()
            assert all(x.matched_by == "candidate" and x.node_id is None for x in r1)

            # ── 审核:approve 其一 + merge 其二 ──
            cand_ap = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == NAME_APPROVE)
            )).scalar_one()
            node = await review.approve(
                db, candidate_id=cand_ap.id, axis="knowledge", stage="初",
                node_kind="句法", reviewer_id=reviewer,
            )
            await db.commit()
            approved_node_id = node.id

            cand_mg = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == NAME_MERGE)
            )).scalar_one()
            await review.merge(db, candidate_id=cand_mg.id,
                               target_node_id=approved_node_id, reviewer_id=reviewer)
            await db.commit()

            # ── Round 2:复跑同样的名 ──
            r2 = await match.match_names(db, ALL, source_type="exam")
            await db.commit()
            by_name = dict(zip(ALL, r2))

            # 已 approve 的 → 命中该节点(归一化精确/别名)
            assert by_name[NAME_APPROVE].node_id == approved_node_id
            # 已 merge 的 → 命中**同一**节点(别名归一,碎片化被治住)
            assert by_name[NAME_MERGE].node_id == approved_node_id
            # 未审的 → 仍只落候选,occur_count 聚合到 2,不建节点
            assert by_name[NAME_MISS].matched_by == "candidate"
            miss = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == NAME_MISS)
            )).scalar_one()
            assert miss.occur_count == 2

            # ── 总断言:净增节点恰为 1(approve 的);零游离 auto_ 节点 ──
            assert await _node_count(db) == nodes_before + 1
            floating = (await db.execute(
                select(func.count()).select_from(KnowledgeNode)
                .where(KnowledgeNode.code.like("auto_%"))
            )).scalar_one()
            assert floating == 0
    finally:
        await _cleanup()
