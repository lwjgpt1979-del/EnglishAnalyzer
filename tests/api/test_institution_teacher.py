"""机构端老师管理 API 测试（D-121）。"""
import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
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
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="138",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()
        return inst.id


async def _admin_login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _teacher_login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=h)).json()["data"]
    uid = uuid.UUID(me["id"])
    async with _async_session_factory() as s:
        u = await s.get(User, uid)
        u.role = "teacher"
        s.add(Teacher(id=uid))
        await s.commit()
    return h, uid


@pytest.mark.asyncio
async def test_invite_join_list_remove_flow(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(uname)
    ah = await _admin_login(client, uname)

    code = (await client.post("/api/v1/institution/teachers/invite-code",
                              headers=ah)).json()["data"]["code"]

    th, tid = await _teacher_login(client, f"t_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/teacher/join-institution", headers=th, json={"code": code})
    assert r.status_code == 200

    rows = (await client.get("/api/v1/institution/teachers", headers=ah)).json()["data"]
    assert any(t["id"] == str(tid) for t in rows)

    r = await client.delete(f"/api/v1/institution/teachers/{tid}", headers=ah)
    assert r.status_code == 200
    rows = (await client.get("/api/v1/institution/teachers", headers=ah)).json()["data"]
    assert not any(t["id"] == str(tid) for t in rows)


@pytest.mark.asyncio
async def test_cross_institution_remove_404(client):
    ua = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(ua, "A")
    ah = await _admin_login(client, ua)
    ub = f"ib_{uuid.uuid4().hex[:6]}"
    b_inst = await _setup_admin(ub, "B")
    async with _async_session_factory() as s:
        btid = uuid.uuid4()
        s.add(User(id=btid, openid=f"o:{btid}", role="teacher"))
        await s.flush()
        s.add(Teacher(id=btid, institution_id=b_inst))
        await s.commit()
    r = await client.delete(f"/api/v1/institution/teachers/{btid}", headers=ah)
    assert r.status_code == 404
