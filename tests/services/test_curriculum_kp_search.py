"""search_kps service TDD 测试。"""
from __future__ import annotations
import pytest
import pytest_asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seed_kps(db: AsyncSession):
    """插入 4 个知识点：2 个含"完成"，1 个含"被动"，1 个其他。"""
    def _kp(name: str) -> KnowledgePoint:
        return KnowledgePoint(
            id=uuid.uuid4(),
            code=f"TST_{uuid.uuid4().hex[:6]}",
            name=name,
            category="grammar",
            applicable_grades=["小学5年级"],
            applicable_textbooks=["译林版"],
        )
    kps = [_kp("现在完成时"), _kp("过去完成时"), _kp("被动语态"), _kp("一般现在时")]
    for k in kps:
        db.add(k)
    await db.flush()
    return kps


@pytest.mark.asyncio
async def test_search_kps_by_keyword(db, seed_kps):
    """关键词"完成"应返回2条，不含"被动"和"一般"。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="完成", limit=10)
    names = [r.name for r in results]
    assert len(results) == 2
    assert "现在完成时" in names
    assert "过去完成时" in names
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
