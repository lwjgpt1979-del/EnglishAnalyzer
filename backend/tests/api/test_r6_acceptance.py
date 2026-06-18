"""R6 验收闭环:node 挂多类型资源(讲解/视频/例句)→ 审核发布 → 学生按 node 只读 published。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.services import node_resource_service as nr

_TAG = "r6acc"


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
async def test_r6_resource_loop():
    node_id = await _seed_node()
    reviewer = uuid.uuid4()
    try:
        # 1) 同一 node 挂三类资源(草稿):讲解(语法)/视频/例句
        async with _async_session_factory() as db:
            lec_id = await nr.upsert_lecture(db, node_id=node_id, dimension="grammar", content_md="语法讲解")
            vid = await nr.add_resource(db, node_id=node_id, resource_type="video",
                                        title="视频", media_url="https://x/v.mp4")
            exa = await nr.add_resource(db, node_id=node_id, resource_type="example",
                                        resource_json=[{"en": "I go.", "zh": "我去。"}])
            await db.commit()
            ids = {lec_id, vid.id, exa.id}

        # 2) 学生此时读不到(全 draft)
        async with _async_session_factory() as db:
            assert await nr.list_published(db, node_id=node_id) == []

        # 3) 三条逐一审核发布
        async with _async_session_factory() as db:
            for rid in ids:
                await nr.review(db, resource_id=rid, approve=True, reviewer_id=reviewer)
            await db.commit()

        # 4) 学生按 node 读到全部 published,类型齐全
        async with _async_session_factory() as db:
            pub = await nr.list_published(db, node_id=node_id)
            assert {r.id for r in pub} == ids
            assert {r.resource_type for r in pub} == {"lecture", "video", "example"}
            # 按类型过滤
            only_video = await nr.list_published(db, node_id=node_id, resource_type="video")
            assert len(only_video) == 1 and only_video[0].id == vid.id
    finally:
        await _cleanup(node_id)
