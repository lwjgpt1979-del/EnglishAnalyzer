"""R0.3 受控匹配 smoke:精确/受控(dev 包含代理)/模糊/候选累加 + use_llm=False + skip。

核心验收(§7):复跑同类内容不再产生游离节点——miss 只让候选 occur_count++,
knowledge_nodes 不新增。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text, func

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.services.kp_normalize import normalize_kp_name
from app.services import kp_match_service as svc

_TAG = "kpmatch"  # 纯 ASCII,归一化后保留,便于隔离清理


async def _seed_nodes() -> dict[str, uuid.UUID]:
    """两个标准节点 + 别名:'一般现在时'、'定语从句'(均带 _TAG 前缀)。"""
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    names = {a_id: f"{_TAG}一般现在时", b_id: f"{_TAG}定语从句"}
    async with _async_session_factory() as db:
        for i, (nid, name) in enumerate(names.items()):
            db.add(KnowledgeNode(
                id=nid, axis="knowledge", node_kind="句法",
                name=name, code=f"{_TAG}-n{i}", status="active", source="seed",
            ))
            await db.flush()
            db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=name,
                             alias_norm=normalize_kp_name(name), source="seed"))
        await db.commit()
    return {"a": a_id, "b": b_id}


async def _cleanup() -> None:
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_match_pipeline():
    ids = await _seed_nodes()
    try:
        async with _async_session_factory() as db:
            # 1) 归一化精确(别名命中)
            r = await svc.match_kp(db, raw_name=f"{_TAG}一般现在时")
            assert r.matched_by == "alias" and r.node_id == ids["a"]

            # 1b) 标点/空白差异仍精确命中(归一化)
            r = await svc.match_kp(db, raw_name=f" {_TAG}一般现在时。")
            assert r.matched_by == "alias" and r.node_id == ids["a"]

            # 2) 受控选择(dev 包含代理):查询包含某节点全名 → 命中该节点
            r = await svc.match_kp(db, raw_name=f"{_TAG}一般现在时辨析")
            assert r.matched_by == "controlled_llm" and r.node_id == ids["a"]

            # 2b) use_llm=False → 跳过受控,转模糊;同串仍由模糊命中
            r = await svc.match_kp(db, raw_name=f"{_TAG}一般现在时辨析", use_llm=False)
            assert r.matched_by == "fuzzy" and r.node_id == ids["a"]

            # 3) 模糊兜底:一字之差、无包含 → fuzzy
            r = await svc.match_kp(db, raw_name=f"{_TAG}定语从勾")
            assert r.matched_by == "fuzzy" and r.node_id == ids["b"]
            assert r.confidence >= svc._FUZZY_THRESHOLD

            # 4) skip:归一化为空
            r = await svc.match_kp(db, raw_name="。。。！！")
            assert r.matched_by == "skip" and r.node_id is None
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_miss_accumulates_candidate_no_floating_node():
    ids = await _seed_nodes()
    try:
        async with _async_session_factory() as db:
            before = (await db.execute(
                select(func.count()).select_from(KnowledgeNode)
            )).scalar()

            miss = f"{_TAG}完全无关概念xyz"
            r1 = await svc.match_kp(db, raw_name=miss, source_type="exam")
            assert r1.matched_by == "candidate" and r1.candidate_id is not None
            assert r1.node_id is None

            # 复跑同名 → occur_count++,不新建候选、不新建节点
            r2 = await svc.match_kp(db, raw_name=miss, source_type="exam")
            assert r2.matched_by == "candidate" and r2.candidate_id == r1.candidate_id

            cand = (await db.execute(
                select(KpCandidate).where(KpCandidate.id == r1.candidate_id)
            )).scalar_one()
            assert cand.occur_count == 2
            assert cand.suggested_axis == "knowledge"   # 非空,决策②
            assert cand.status == "pending"

            after = (await db.execute(
                select(func.count()).select_from(KnowledgeNode)
            )).scalar()
            assert after == before   # 核心:miss 不产生游离节点
    finally:
        await _cleanup()
