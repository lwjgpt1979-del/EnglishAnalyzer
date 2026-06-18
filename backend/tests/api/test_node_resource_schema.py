"""R6.1 node_resource schema:多类型挂 node;lecture 每维度唯一,其它类型可多条。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d19_node_resource import NodeResource

_TAG = "nrsc"


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
async def test_node_resource_types_and_unique():
    node_id = await _seed_node()
    try:
        async with _async_session_factory() as db:
            # lecture 六维度各一 + video/example/mindmap 多条
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="lecture",
                                dimension="grammar", content_md="语法讲解", status="published"))
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="lecture",
                                dimension="reading", content_md="阅读讲解", status="draft"))
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="video",
                                title="视频1", media_url="https://x/v1.mp4", status="published"))
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="video",
                                title="视频2", media_url="https://x/v2.mp4", status="draft"))
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="example",
                                resource_json=[{"en": "I go.", "zh": "我去。"}], status="published"))
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="mindmap",
                                media_url="https://x/mm.png", status="published"))
            await db.commit()

        async with _async_session_factory() as db:
            cnt = (await db.execute(select(func.count()).select_from(NodeResource)
                   .where(NodeResource.node_id == node_id))).scalar_one()
            assert cnt == 6   # 2 lecture + 2 video + 1 example + 1 mindmap

        # lecture 同维度重复 → 唯一约束报错
        async with _async_session_factory() as db:
            db.add(NodeResource(id=uuid.uuid4(), node_id=node_id, resource_type="lecture",
                                dimension="grammar", content_md="重复语法"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    finally:
        await _cleanup(node_id)
