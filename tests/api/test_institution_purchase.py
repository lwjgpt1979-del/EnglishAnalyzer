"""机构学生采购 + 激活 API 测试（D-122）。"""
import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Student, User
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _setup_admin(username, inst_name="机构A"):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()
        return inst.id


async def _admin_login(client, username):
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _student_login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=h)).json()["data"]
    uid = uuid.UUID(me["id"])
    async with _async_session_factory() as s:
        u = await s.get(User, uid)
        u.role = "student"
        s.add(Student(id=uid))
        await s.commit()
    return h, uid


@pytest.mark.asyncio
async def test_purchase_to_activation_flow(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(uname)
    ah = await _admin_login(client, uname)

    r = await client.post("/api/v1/institution/purchases", headers=ah,
                          json={"tier": "pro", "duration_months": 6, "quantity": 2})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["quantity"] == 2 and len(data["codes"]) == 2
    code = data["codes"][0]["code"]

    rows = (await client.get("/api/v1/institution/purchases", headers=ah)).json()["data"]
    assert rows[0]["total_count"] == 2 and rows[0]["used_count"] == 0

    sh, sid = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/memberships/activate-code", headers=sh, json={"code": code})
    assert r.status_code == 200

    me = (await client.get("/api/v1/memberships/me", headers=sh)).json()["data"]
    assert me["tier"] == "pro"


@pytest.mark.asyncio
async def test_activate_used_code_400(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(uname)
    ah = await _admin_login(client, uname)
    code = (await client.post("/api/v1/institution/purchases", headers=ah,
            json={"tier": "basic", "duration_months": 1, "quantity": 1})).json()["data"]["codes"][0]["code"]
    sh, _ = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    await client.post("/api/v1/memberships/activate-code", headers=sh, json={"code": code})
    sh2, _ = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/memberships/activate-code", headers=sh2, json={"code": code})
    assert r.status_code == 400
