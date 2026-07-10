"""search_kps service TDD 测试。"""
from __future__ import annotations
import pytest
import pytest_asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import _async_session_factory
# R8 Phase5b:search_kps 已改搜 knowledge_nodes(单一真源),种子改建 KnowledgeNode
from app.models.d15_knowledge_graph import KnowledgeNode


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


# 唯一标记词：避免与生产库已有的真实知识点（如"现在完成时"）名称碰撞，
# 使关键词精确匹配类测试不受 DB 已有种子数据影响。
_TAG = uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def seed_kps(db: AsyncSession):
    """插入 4 个知识 node：2 个含唯一标记词，1 个含"被动"，1 个其他。"""
    def _kp(name: str) -> KnowledgeNode:
        return KnowledgeNode(
            id=uuid.uuid4(),
            axis="knowledge",
            node_kind="grammar",
            name=name,
            code=f"TST_{uuid.uuid4().hex[:6]}",
            status="active",
        )
    kps = [_kp(f"现在完成时{_TAG}"), _kp(f"过去完成时{_TAG}"), _kp("被动语态"), _kp("一般现在时")]
    for k in kps:
        db.add(k)
    await db.flush()
    return kps


@pytest.mark.asyncio
async def test_search_kps_by_keyword(db, seed_kps):
    """按唯一标记词搜索应恰好返回本测试 seed 的 2 条，不含其他。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q=_TAG, limit=10)
    names = [r.name for r in results]
    assert len(results) == 2
    assert f"现在完成时{_TAG}" in names
    assert f"过去完成时{_TAG}" in names
    assert "被动语态" not in names


@pytest.mark.asyncio
async def test_search_kps_empty_query_returns_all(db, seed_kps):
    """空字符串不过滤，返回 limit 条。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="", limit=10)
    assert len(results) >= 4


@pytest.mark.asyncio
async def test_search_kps_no_match_returns_empty(db, seed_kps):
    """无匹配时返回空列表，不报错。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="不可能存在的知识点XYZ", limit=10)
    assert results == []


@pytest.mark.asyncio
async def test_search_kps_respects_limit(db, seed_kps):
    """limit 参数生效：limit=2 最多返回 2 条。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="", limit=2)
    assert len(results) <= 2
