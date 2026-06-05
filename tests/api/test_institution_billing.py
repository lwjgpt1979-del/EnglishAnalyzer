"""机构账单 API 测试（D-125）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution
from app.services import admin_auth_service, institution_purchase_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _setup(username, inst_name="机构A"):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        admin = await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.flush()
        await institution_purchase_service.create_purchase(
            s, institution_id=inst.id, created_by=admin.id,
            tier="pro", duration_months=6, quantity=1)
        await s.commit()
        return inst.id


async def _login(client, username):
    # 机构管理员走机构登录门（D-129）
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_list_bills_api(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup(uname)
    h = await _login(client, uname)
    r = await client.get("/api/v1/institution/bills", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(b["type"] == "采购" for b in data)


@pytest.mark.asyncio
async def test_platform_admin_forbidden(client):
    uname = f"pa_{uuid.uuid4().hex[:6]}"
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=uname, password="pw123456")
        await s.commit()
    # platform_admin 走平台登录门
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": uname, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = await client.get("/api/v1/institution/bills", headers=h)
    assert r.status_code == 403
