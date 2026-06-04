"""机构入驻审核 API 测试（D-123，超管侧）。"""
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


async def _platform_admin(client, username):
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password="pw123456")
        await s.commit()
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_create_list_approve_flow(client):
    h = await _platform_admin(client, f"pa_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/admin/institutions", headers=h, json={
        "name": "机构X", "contact_phone": "138", "province_code": "11",
        "city_code": "1101", "address": "街"})
    assert r.status_code == 200
    inst_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "pending"

    rows = (await client.get("/api/v1/admin/institutions?status=pending", headers=h)).json()["data"]
    assert any(i["id"] == inst_id for i in rows)

    uname = f"ia_{uuid.uuid4().hex[:6]}"
    r = await client.post(f"/api/v1/admin/institutions/{inst_id}/approve",
                          headers=h, json={"admin_username": uname})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["admin_username"] == uname and len(data["password"]) >= 8

    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": uname, "password": data["password"]})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reject(client):
    h = await _platform_admin(client, f"pa_{uuid.uuid4().hex[:6]}")
    inst_id = (await client.post("/api/v1/admin/institutions", headers=h, json={
        "name": "Y", "contact_phone": "1", "province_code": "11",
        "city_code": "1101", "address": "街"})).json()["data"]["id"]
    r = await client.post(f"/api/v1/admin/institutions/{inst_id}/reject", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "suspended"


@pytest.mark.asyncio
async def test_institution_admin_forbidden(client):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        uname = f"ia_{uuid.uuid4().hex[:6]}"
        await admin_auth_service.create_institution_admin(
            s, username=uname, password="pw123456", institution_id=inst.id)
        await s.commit()
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": uname, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = await client.get("/api/v1/admin/institutions", headers=h)
    assert r.status_code == 403
