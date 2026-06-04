"""机构批量续费 API 测试（D-124）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import admin_auth_service


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
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        sid = uuid.uuid4()
        s.add(User(id=sid, openid=f"o:{sid}", role="student", nickname="学生"))
        await s.flush()
        s.add(Student(id=sid, institution_id=inst.id))
        now = dt.datetime.now(dt.timezone.utc)
        s.add(Membership(id=uuid.uuid4(), user_id=sid, tier="pro", started_at=now,
                         expires_at=now + dt.timedelta(days=10), is_active=True))
        await s.commit()
        return inst.id, sid


async def _login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_list_and_batch_renew(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    _, sid = await _setup(uname)
    h = await _login(client, uname)

    rows = (await client.get("/api/v1/institution/renewable-students", headers=h)).json()["data"]
    assert any(r["student_id"] == str(sid) for r in rows)
    before = next(r for r in rows if r["student_id"] == str(sid))["expires_at"]

    r = await client.post("/api/v1/institution/batch-renew", headers=h,
                          json={"student_ids": [str(sid)], "duration_months": 6})
    assert r.status_code == 200
    assert r.json()["data"]["renewed_count"] == 1

    rows2 = (await client.get("/api/v1/institution/renewable-students", headers=h)).json()["data"]
    after = next(r for r in rows2 if r["student_id"] == str(sid))["expires_at"]
    assert after > before
