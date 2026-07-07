"""课程发布闸门:学生 list_units 只见 published;发布/下架切换;整学期批量。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.services import curriculum_service as cs


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _unit(s, *, unit_no, status, tv="测试版PUB", grade="初中7年级", sem="上"):
    u = CurriculumUnit(id=uuid.uuid4(), textbook_version=tv, grade=grade, semester=sem,
                       unit_no=unit_no, unit_title=f"U{unit_no}", status=status)
    s.add(u)
    await s.flush()
    return u


@pytest.mark.asyncio
async def test_list_units_only_published(db_session):
    await _unit(db_session, unit_no=1, status="published")
    await _unit(db_session, unit_no=2, status="draft")
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版PUB", grade="初中7年级", semester="上")
    nos = {o.unit_no for o in out}
    assert 1 in nos and 2 not in nos          # 学生只见已发布


@pytest.mark.asyncio
async def test_list_units_grade_normalized_and_published(db_session):
    await _unit(db_session, unit_no=1, status="published")
    # 学生传旧格式「七年级」也应命中已发布的 初中7年级
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版PUB", grade="七年级", semester="上")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_toggle_and_bulk_status(db_session):
    u = await _unit(db_session, unit_no=1, status="draft")
    await cs.set_unit_status(db_session, unit_id=u.id, status="published")
    assert (await db_session.get(CurriculumUnit, u.id)).status == "published"
    # 整学期下架
    await _unit(db_session, unit_no=2, status="published")
    n = await cs.set_units_status_bulk(db_session, textbook_version="测试版PUB",
                                       grade="初中7年级", semester="上", status="draft")
    assert n >= 2
    out = await cs.list_units(db_session, user_id=uuid.uuid4(),
                              textbook_version="测试版PUB", grade="初中7年级", semester="上")
    assert out == []
