"""pricing_service 测试（M5 / D-097 运营定价配置）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.schemas.semesters import SemesterPricing
from app.services import pricing_service
from app.services.auth_service import upsert_user


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _make_admin_id() -> uuid.UUID:
    async with _async_session_factory() as s:
        u = await upsert_user(s, openid=f"pricing_admin_{uuid.uuid4().hex[:6]}")
        await s.commit()
        return u.id


@pytest.mark.asyncio
async def test_update_then_get_roundtrip(db_session):
    """update_semester_pricing 写入后，get_semester_pricing 读到新值。"""
    admin_id = await _make_admin_id()
    new = SemesterPricing(basic=49, pro=89, promax=169)
    await pricing_service.update_semester_pricing(
        db_session, pricing=new, updated_by=admin_id,
    )
    await db_session.flush()
    got = await pricing_service.get_semester_pricing(db_session)
    assert (got.basic, got.pro, got.promax) == (49, 89, 169)


@pytest.mark.asyncio
async def test_update_is_idempotent_upsert(db_session):
    """重复 update 不产生重复行（key 唯一），读到最后一次的值。"""
    admin_id = await _make_admin_id()
    await pricing_service.update_semester_pricing(
        db_session, pricing=SemesterPricing(basic=10, pro=20, promax=30),
        updated_by=admin_id,
    )
    await db_session.flush()
    await pricing_service.update_semester_pricing(
        db_session, pricing=SemesterPricing(basic=11, pro=22, promax=33),
        updated_by=admin_id,
    )
    await db_session.flush()
    got = await pricing_service.get_semester_pricing(db_session)
    assert (got.basic, got.pro, got.promax) == (11, 22, 33)
