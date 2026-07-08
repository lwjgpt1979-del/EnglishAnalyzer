"""教材主数据(curriculum_catalog)= 版本/年级/学期 唯一真源 + 上下架。

学生 list_units 以 catalog 组合上架为闸门;preference_options 从 catalog 派生;
catalog 增/上下架/删 round-trip。上下架已从单元页移到目录级。
"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit, CurriculumCatalog
from app.services import curriculum_service as cs
from app.services import curriculum_catalog_service as cat


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _unit(s, *, unit_no, tv, grade="初中7年级", sem="上"):
    u = CurriculumUnit(id=uuid.uuid4(), textbook_version=tv, grade=grade, semester=sem,
                       unit_no=unit_no, unit_title=f"U{unit_no}", status="published")
    s.add(u)
    await s.flush()
    return u


async def _cat(s, *, tv, status, grade="初中7年级", sem="上"):
    c = CurriculumCatalog(id=uuid.uuid4(), textbook_version=tv, grade=grade, semester=sem, status=status)
    s.add(c)
    await s.flush()
    return c


@pytest.mark.asyncio
async def test_list_units_gated_by_catalog(db_session):
    """组合已上架 → 单元可见;仅有单元但目录未建/下架 → 学生看不到。"""
    await _unit(db_session, unit_no=1, tv="测试版CAT")
    # 无目录行 → 闸门关闭
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版CAT", grade="初中7年级", semester="上")
    assert out == []
    # 建目录但下架 → 仍不可见
    c = await _cat(db_session, tv="测试版CAT", status="draft")
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版CAT", grade="初中7年级", semester="上")
    assert out == []
    # 上架 → 可见
    c.status = "published"
    await db_session.flush()
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版CAT", grade="初中7年级", semester="上")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_list_units_grade_normalized(db_session):
    """学生传旧格式「七年级」也应命中已上架的 初中7年级 组合。"""
    await _unit(db_session, unit_no=1, tv="测试版CAT2")
    await _cat(db_session, tv="测试版CAT2", status="published")
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版CAT2", grade="七年级", semester="上")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_preference_options_from_catalog(db_session):
    """版本/年级/学期均从 catalog 派生:消费侧只见上架组合;admin 见全部。
    用不与真实数据碰撞的自定义年级/学期取值,隔离验证过滤逻辑(不受库内 译林版 存量影响)。"""
    await _cat(db_session, tv="测试版OPT", status="published", grade="测试上架年级", sem="测秋")
    await _cat(db_session, tv="测试版OPT", status="draft", grade="测试下架年级", sem="测冬")

    c = await cat.preference_options(db_session)                       # 消费侧
    assert "测试版OPT" in c["textbook_versions"]
    assert "测试上架年级" in c["grades"] and "测试下架年级" not in c["grades"]   # 下架组合不泄露给 C 端
    assert "测秋" in c["semesters"] and "测冬" not in c["semesters"]

    a = await cat.preference_options(db_session, include_unpublished=True)   # admin 全见
    assert "测试下架年级" in a["grades"] and "测冬" in a["semesters"]

    # 委托一致:curriculum_service.preference_options 等价
    assert await cs.preference_options(db_session) == c


@pytest.mark.asyncio
async def test_catalog_write_roundtrip(db_session):
    """新增(默认下架)→ 上架 → is_published → 删除。写方法自带 commit,末尾删除自清理。"""
    tv = "测试版CATW"
    row = await cat.add_offering(db_session, textbook_version=tv, grade="初中9年级", semester="上")
    try:
        assert row["status"] == "draft"                                # 新增默认下架
        assert not await cat.is_published(db_session, textbook_version=tv, grade="初中9年级", semester="上")
        await cat.set_status(db_session, catalog_id=uuid.UUID(row["id"]), status="published")
        assert await cat.is_published(db_session, textbook_version=tv, grade="初中9年级", semester="上")
    finally:
        n = await cat.delete_offering(db_session, catalog_id=uuid.UUID(row["id"]))
        assert n == 1
