"""机构/平台登录门拆分测试（D-129）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _mk_inst_admin(username):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()


async def _mk_platform_admin(username):
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password="pw123456")
        await s.commit()


@pytest.mark.asyncio
async def test_institution_login_ok(client):
    u = f"ia_{uuid.uuid4().hex[:6]}"
    await _mk_inst_admin(u)
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_platform_cannot_login_institution_door(client):
    u = f"pa_{uuid.uuid4().hex[:6]}"
    await _mk_platform_admin(u)
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_institution_cannot_login_admin_door(client):
    u = f"ia2_{uuid.uuid4().hex[:6]}"
    await _mk_inst_admin(u)
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 401
