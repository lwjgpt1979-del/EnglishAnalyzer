"""R6.2 资源服务:lecture upsert(同维度更新)/ 加资源 / 审核发布 / 学生只读 published。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d19_node_resource import NodeResource
from app.services import node_resource_service as nr

_TAG = "nrsvc"


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.commit()
    return nid


async def _cleanup(node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM node_resource WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_resource_lifecycle():
    node_id = await _seed_node()
    try:
        async with _async_session_factory() as db:
            # lecture upsert:同维度二次写 → 同一行、正文更新
            rid1 = await nr.upsert_lecture(db, node_id=node_id, dimension="grammar", content_md="v1")
            rid2 = await nr.upsert_lecture(db, node_id=node_id, dimension="grammar", content_md="v2")
            await db.commit()
            assert rid1 == rid2
        async with _async_session_factory() as db:
            r = (await db.execute(select(NodeResource).where(NodeResource.id == rid1))).scalar_one()
            assert r.content_md == "v2"
            cnt = (await db.execute(select(func.count()).select_from(NodeResource)
                   .where(NodeResource.node_id == node_id))).scalar_one()
            assert cnt == 1   # upsert 不新增

        # 加视频(draft)→ 审核发布
        async with _async_session_factory() as db:
            vid = await nr.add_resource(db, node_id=node_id, resource_type="video",
                                        title="讲解视频", media_url="https://x/v.mp4")
            await db.commit()
            video_id = vid.id
        async with _async_session_factory() as db:
            await nr.review(db, resource_id=video_id, approve=True, reviewer_id=uuid.uuid4())
            await db.commit()

        # 学生只读 published(video 已发布;lecture grammar 仍 draft → 不可见)
        async with _async_session_factory() as db:
            pub = await nr.list_published(db, node_id=node_id)
            ids = {r.id for r in pub}
            assert video_id in ids and rid1 not in ids
            # 审核队列默认看 draft → 含 lecture
            rows, total = await nr.list_for_review(db, status="draft", node_id=node_id)
            assert any(r.id == rid1 for r in rows)
    finally:
        await _cleanup(node_id)
