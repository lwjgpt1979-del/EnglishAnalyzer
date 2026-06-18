"""生成内容不丢:KP 未命中 node → pending_kp_content 暂存 → 候选 approve/merge 物化为 lecture。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d11_v2_curriculum import PendingKpContent
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d19_node_resource import NodeResource
from app.services import curriculum_service, kp_candidate_service
from app.services.kp_normalize import normalize_kp_name

_TAG = "pendkp"


@pytest_asyncio.fixture
async def db():
    async with _async_session_factory() as s:
        yield s


async def _cleanup_norm(norm: str, node_id: uuid.UUID | None = None):
    async with _async_session_factory() as s:
        await s.execute(text("DELETE FROM pending_kp_content WHERE kp_name_norm = :n"), {"n": norm})
        if node_id is not None:
            await s.execute(text("DELETE FROM node_resource WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(text("DELETE FROM knowledge_node_aliases WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(text("DELETE FROM knowledge_nodes WHERE id = :n"), {"n": str(node_id)})
        await s.execute(text("DELETE FROM kp_candidates WHERE name_norm = :n"), {"n": norm})
        await s.commit()


@pytest.mark.asyncio
async def test_stash_pending_content_upserts_by_norm_dim(db):
    """_stash_pending_content 按 (norm, dimension) upsert。"""
    name = f"{_TAG}_暂存_{uuid.uuid4().hex[:6]}"
    norm = normalize_kp_name(name)
    try:
        await curriculum_service._stash_pending_content(
            db, kp_name=name, dimension="grammar", content_md="语法v1", source_unit_id=None)
        await curriculum_service._stash_pending_content(
            db, kp_name=name, dimension="reading", content_md="阅读v1", source_unit_id=None)
        # 同 (norm,grammar) 再写 → 覆盖不新增
        await curriculum_service._stash_pending_content(
            db, kp_name=name, dimension="grammar", content_md="语法v2", source_unit_id=None)
        await db.commit()
        rows = (await db.execute(
            select(PendingKpContent).where(PendingKpContent.kp_name_norm == norm)
        )).scalars().all()
        assert {r.dimension for r in rows} == {"grammar", "reading"}
        gram = next(r for r in rows if r.dimension == "grammar")
        assert gram.content_md == "语法v2"
    finally:
        await _cleanup_norm(norm)


@pytest.mark.asyncio
async def test_approve_materializes_pending_into_node_resource(db):
    """候选 approve 出 node → pending 物化为 node_resource lecture(draft)+ pending 行清除。"""
    name = f"{_TAG}_物化_{uuid.uuid4().hex[:6]}"
    norm = normalize_kp_name(name)
    cid = uuid.uuid4()
    async with _async_session_factory() as s:
        await curriculum_service._stash_pending_content(
            s, kp_name=name, dimension="grammar", content_md="语法讲解", source_unit_id=None)
        await curriculum_service._stash_pending_content(
            s, kp_name=name, dimension="writing", content_md="写作讲解", source_unit_id=None)
        s.add(KpCandidate(id=cid, raw_name=name, name_norm=norm, suggested_axis="knowledge",
                          occur_count=1, source_type="textbook", status="pending"))
        await s.commit()

    node_id = None
    try:
        node = await kp_candidate_service.approve(
            db, candidate_id=cid, axis="knowledge", reviewer_id=uuid.uuid4())
        await db.commit()
        node_id = node.id

        async with _async_session_factory() as s:
            lectures = (await s.execute(
                select(NodeResource).where(
                    NodeResource.node_id == node_id, NodeResource.resource_type == "lecture")
            )).scalars().all()
            assert {l.dimension for l in lectures} == {"grammar", "writing"}
            assert all(str(l.status) == "draft" for l in lectures)
            # pending 已清除
            left = (await s.execute(
                select(PendingKpContent).where(PendingKpContent.kp_name_norm == norm)
            )).scalars().all()
            assert left == []
    finally:
        await _cleanup_norm(norm, node_id)


@pytest.mark.asyncio
async def test_merge_materializes_pending_into_target_node(db):
    """候选 merge 到既有 node → pending 物化到该 target node。"""
    name = f"{_TAG}_并_{uuid.uuid4().hex[:6]}"
    norm = normalize_kp_name(name)
    target_name = f"{_TAG}_目标_{uuid.uuid4().hex[:6]}"
    cid, nid = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="语法", name=target_name,
                            code=f"{_TAG}-{uuid.uuid4().hex[:6]}", status="active", source="seed"))
        await s.flush()
        s.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=target_name,
                        alias_norm=normalize_kp_name(target_name), source="seed"))
        await curriculum_service._stash_pending_content(
            s, kp_name=name, dimension="reading", content_md="阅读讲解", source_unit_id=None)
        s.add(KpCandidate(id=cid, raw_name=name, name_norm=norm, suggested_axis="knowledge",
                          occur_count=1, source_type="textbook", status="pending"))
        await s.commit()
    try:
        await kp_candidate_service.merge(db, candidate_id=cid, target_node_id=nid,
                                         reviewer_id=uuid.uuid4())
        await db.commit()
        async with _async_session_factory() as s:
            lectures = (await s.execute(
                select(NodeResource).where(
                    NodeResource.node_id == nid, NodeResource.resource_type == "lecture")
            )).scalars().all()
            assert {l.dimension for l in lectures} == {"reading"}
            left = (await s.execute(
                select(PendingKpContent).where(PendingKpContent.kp_name_norm == norm)
            )).scalars().all()
            assert left == []
    finally:
        await _cleanup_norm(norm, nid)
