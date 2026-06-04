"""机构管理员账号认证测试（D-120）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _institution(s) -> Institution:
    inst = Institution(
        id=uuid.uuid4(), name="测试机构", contact_phone="13800000000",
        province_code="11", city_code="1101", address="某街1号",
    )
    s.add(inst)
    await s.flush()
    return inst


@pytest.mark.asyncio
async def test_create_and_authenticate_institution_admin(db_session):
    inst = await _institution(db_session)
    username = f"inst_admin_{uuid.uuid4().hex[:6]}"

    admin = await admin_auth_service.create_institution_admin(
        db_session, username=username, password="pw123456", institution_id=inst.id,
    )
    await db_session.flush()
    assert str(admin.role) == "institution_admin"
    assert admin.institution_id == inst.id

    ok = await admin_auth_service.authenticate(
        db_session, username=username, password="pw123456",
    )
    assert ok is not None and ok.id == admin.id

    bad = await admin_auth_service.authenticate(
        db_session, username=username, password="wrong",
    )
    assert bad is None
