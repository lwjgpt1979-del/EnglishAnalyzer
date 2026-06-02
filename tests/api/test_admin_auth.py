"""运营管理员登录 API 测试（M5 / D-098）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _make_admin(username: str, password: str) -> None:
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password=password)
        await s.commit()


@pytest.mark.asyncio
async def test_login_then_call_admin_api(client):
    uname = f"ops_{uuid.uuid4().hex[:6]}"
    await _make_admin(uname, "pw123456")
    r = await client.post(
        "/api/v1/admin/auth/login", json={"username": uname, "password": "pw123456"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    h = {"Authorization": f"Bearer {data['access_token']}"}
    r2 = await client.get("/api/v1/admin/pricing", headers=h)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_401(client):
    uname = f"ops_{uuid.uuid4().hex[:6]}"
    await _make_admin(uname, "pw123456")
    r = await client.post(
        "/api/v1/admin/auth/login", json={"username": uname, "password": "nope"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_401(client):
    r = await client.post(
        "/api/v1/admin/auth/login",
        json={"username": f"ghost_{uuid.uuid4().hex[:6]}", "password": "whatever"},
    )
    assert r.status_code == 401
