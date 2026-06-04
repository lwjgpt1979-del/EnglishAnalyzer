"""机构后台 API 测试（D-120）：概览 + 资料 + 角色隔离。"""
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


async def _setup_inst_admin(username, inst_name="机构A") -> Institution:
    async with _async_session_factory() as s:
        inst = Institution(
            id=uuid.uuid4(), name=inst_name, contact_phone="13800000000",
            province_code="11", city_code="1101", address="某街1号",
        )
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id,
        )
        await s.commit()
        return inst


async def _login(client, username, password="pw123456"):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_overview_and_profile(client):
    username = f"instadmin_{uuid.uuid4().hex[:6]}"
    inst = await _setup_inst_admin(username)
    token = await _login(client, username)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/institution/overview", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert set(body) == {"teacher_count", "student_count", "member_count", "active_7d_count"}

    r = await client.get("/api/v1/institution/profile", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == inst.name

    r = await client.patch("/api/v1/institution/profile", headers=h,
                           json={"name": "新机构名"})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "新机构名"


@pytest.mark.asyncio
async def test_platform_admin_forbidden(client):
    username = f"padmin_{uuid.uuid4().hex[:6]}"
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password="pw123456")
        await s.commit()
    token = await _login(client, username)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/v1/institution/overview", headers=h)
    assert r.status_code == 403
