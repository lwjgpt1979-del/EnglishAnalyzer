"""老师额度 API 测试（D-128）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Teacher, User
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
        tid = uuid.uuid4()
        s.add(User(id=tid, openid=f"o:{tid}", role="teacher", nickname="王老师"))
        await s.flush()
        s.add(Teacher(id=tid, institution_id=inst.id))
        await s.commit()
        return inst.id, tid


async def _login(client, username):
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_set_quota_and_list(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    _, tid = await _setup_admin(uname)
    h = await _login(client, uname)
    r = await client.patch(f"/api/v1/institution/teachers/{tid}/quota",
                           headers=h, json={"monthly_paper_quota": 10})
    assert r.status_code == 200
    assert r.json()["data"]["monthly_paper_quota"] == 10
    rows = (await client.get("/api/v1/institution/teachers", headers=h)).json()["data"]
    assert any(t["id"] == str(tid) and t["monthly_paper_quota"] == 10 for t in rows)
