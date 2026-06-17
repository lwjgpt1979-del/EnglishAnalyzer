"""R0.2 种子迁移 smoke:标准点→节点+别名、auto_→候选、幂等、冲突跳过。

只处理本测试注入的 code(migrate(only_codes=...)),不污染全库。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from migrate_kp_to_node import migrate  # noqa: E402

_TAG = "seedmig"


async def _seed_old_kps() -> dict[str, str]:
    """注入 2 标准点(父子)+ 1 游离 auto_ 点,返回 {role: code}。"""
    root_code = f"{_TAG}-syntax"
    child_code = f"{_TAG}-attr-clause"
    auto_code = f"auto_{_TAG}_past_perfect_abc12345"
    async with _async_session_factory() as db:
        root = KnowledgePoint(
            id=uuid.uuid4(), code=root_code, name=f"{_TAG}句法", category="grammar",
            applicable_grades=["初中7年级"], applicable_textbooks=["译林版"],
            sort_order=0,
        )
        db.add(root)
        await db.flush()
        child = KnowledgePoint(
            id=uuid.uuid4(), code=child_code, name=f"{_TAG}定语从句", category="grammar",
            applicable_grades=["初中7年级", "高中1年级"], applicable_textbooks=["译林版"],
            parent_id=root.id, sort_order=1,
        )
        # 同名重复行(不同 code、同名 root)→ 应折叠进 root 节点,并把"高"学段并集进来
        dup_code = f"{_TAG}-syntax-dup"
        dup = KnowledgePoint(
            id=uuid.uuid4(), code=dup_code, name=f"{_TAG}句法", category="grammar",
            applicable_grades=["高中1年级"], applicable_textbooks=["人教版"], sort_order=0,
        )
        auto = KnowledgePoint(
            id=uuid.uuid4(), code=auto_code, name=f"{_TAG}过去完成时", category="grammar",
            applicable_grades=["初中7年级"], applicable_textbooks=[], sort_order=0,
        )
        db.add_all([child, dup, auto])
        await db.commit()
        return {"root": root_code, "child": child_code, "dup": dup_code, "auto": auto_code}


async def _cleanup(codes: dict[str, uuid.UUID]) -> None:
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"%{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm LIKE :p"), {"p": f"%{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_points WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_points WHERE code LIKE :p"), {"p": f"auto_{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_seed_migration_idempotent():
    codes = await _seed_old_kps()
    only = {codes["root"], codes["child"], codes["dup"], codes["auto"]}
    try:
        # ── 首次迁移 ──
        st = await migrate(dry=False, only_codes=only)
        assert st.nodes == 2          # root + child(dup 折叠进 root,不新建)
        assert st.collapsed == 1      # dup 同名折叠
        assert st.cand == 1           # auto_ → 候选
        assert st.parents == 1        # child.parent 回填
        assert st.aliases == 2

        async with _async_session_factory() as db:
            # 标准点 → active 节点
            root_node = (await db.execute(
                select(KnowledgeNode).where(KnowledgeNode.code == codes["root"])
            )).scalar_one()
            child_node = (await db.execute(
                select(KnowledgeNode).where(KnowledgeNode.code == codes["child"])
            )).scalar_one()
            assert root_node.axis == "knowledge" and root_node.node_kind == "句法"
            assert root_node.status == "active" and root_node.source == "seed"
            # dup 折叠进 root → 学段并集 初(root) + 高(dup)
            assert set(root_node.applicable_stages) == {"初", "高"}
            # parent 接树
            assert child_node.parent_id == root_node.id
            # 学段映射 初+高
            assert set(child_node.applicable_stages) == {"初", "高"}
            # 名进别名(供受控匹配精确命中)
            alias = (await db.execute(
                select(NodeAlias).where(NodeAlias.node_id == child_node.id)
            )).scalar_one()
            assert alias.alias == f"{_TAG}定语从句"
            # auto_ → 候选 pending,axis 非空(决策②)
            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.source_type == "legacy_auto",
                                          KpCandidate.raw_name == f"{_TAG}过去完成时")
            )).scalar_one()
            assert cand.status == "pending"
            assert cand.suggested_axis == "knowledge"
            assert cand.occur_count == 1

        # ── 复跑:幂等,节点不新增、候选 occur_count++ ──
        st2 = await migrate(dry=False, only_codes=only)
        assert st2.nodes == 0 and st2.nodes_skip == 2   # code 已存在 → 跳过
        assert st2.cand == 0 and st2.cand_bumped == 1   # 同名候选累加,不产新游离点

        async with _async_session_factory() as db:
            node_count = len((await db.execute(
                select(KnowledgeNode).where(KnowledgeNode.code.like(f"{_TAG}%"))
            )).scalars().all())
            assert node_count == 2  # 复跑后仍是 2,无碎片
            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.raw_name == f"{_TAG}过去完成时")
            )).scalar_one()
            assert cand.occur_count == 2
    finally:
        await _cleanup(codes)
