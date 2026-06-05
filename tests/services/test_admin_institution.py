"""机构入驻审核 service 测试（D-123）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services import admin_institution_service as svc
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_create_institution_pending(db_session):
    inst = await svc.create_institution(
        db_session, name="新东方", contact_phone="13800000000",
        province_code="11", city_code="1101", address="海淀区1号")
    assert str(inst.status) == "pending"


@pytest.mark.asyncio
async def test_approve_creates_admin(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    inst2, username, password = await svc.approve_institution(
        db_session, institution_id=inst.id, admin_username=uname)
    assert str(inst2.status) == "active"
    assert username == uname and len(password) >= 8
    user = await admin_auth_service.authenticate(
        db_session, username=uname, password=password,
        allowed_roles=("institution_admin",))
    assert user is not None and str(user.role) == "institution_admin"
    assert user.institution_id == inst.id


@pytest.mark.asyncio
async def test_approve_non_pending_rejected(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    await svc.approve_institution(db_session, institution_id=inst.id, admin_username=f"x_{uuid.uuid4().hex[:6]}")
    with pytest.raises(AppError):
        await svc.approve_institution(db_session, institution_id=inst.id, admin_username=f"y_{uuid.uuid4().hex[:6]}")


@pytest.mark.asyncio
async def test_reject_suspends(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    inst2 = await svc.reject_institution(db_session, institution_id=inst.id)
    assert str(inst2.status) == "suspended"


@pytest.mark.asyncio
async def test_list_filter_by_status(db_session):
    a = await svc.create_institution(db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    b = await svc.create_institution(db_session, name="B", contact_phone="2",
        province_code="11", city_code="1101", address="街")
    await svc.reject_institution(db_session, institution_id=b.id)
    pendings = await svc.list_institutions(db_session, status="pending")
    assert all(str(i.status) == "pending" for i in pendings)
    assert any(i.id == a.id for i in pendings)
    assert all(i.id != b.id for i in pendings)
