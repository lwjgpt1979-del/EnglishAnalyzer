"""R0.1 知识图谱骨架建表 smoke：树/别名唯一/候选唯一。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "kgschema"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_knowledge_graph_tables():
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        root_id, child_id = uuid.uuid4(), uuid.uuid4()
        try:
            # 树：root + child（self-FK）
            db.add(KnowledgeNode(id=root_id, axis="knowledge", node_kind="句法",
                                 name=f"{_TAG}_句法", code=f"{_TAG}_syntax"))
            await db.flush()
            db.add(KnowledgeNode(id=child_id, axis="knowledge", node_kind="句法",
                                 parent_id=root_id, name=f"{_TAG}_定语从句",
                                 code=f"{_TAG}_attr_clause", applicable_stages=["初", "高"]))
            await db.flush()

            # 别名：alias_norm 唯一
            db.add(NodeAlias(id=uuid.uuid4(), node_id=child_id, alias="定语从句",
                             alias_norm=f"{_TAG}_dingyu"))
            await db.flush()
            # 重复 alias_norm → 唯一约束报错
            db.add(NodeAlias(id=uuid.uuid4(), node_id=root_id, alias="x",
                             alias_norm=f"{_TAG}_dingyu"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()

            # 候选：(name_norm, suggested_axis) 唯一
            db.add(KpCandidate(id=uuid.uuid4(), raw_name="过去完成时态",
                               name_norm=f"{_TAG}_pastperfect", suggested_axis="knowledge"))
            await db.flush()
            db.add(KpCandidate(id=uuid.uuid4(), raw_name="过去完成时",
                               name_norm=f"{_TAG}_pastperfect", suggested_axis="knowledge"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
        finally:
            async with sf() as db2:
                await db2.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm LIKE :p"), {"p": f"{_TAG}_%"})
                await db2.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}_%"})
                await db2.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
                await db2.commit()
    await engine.dispose()
