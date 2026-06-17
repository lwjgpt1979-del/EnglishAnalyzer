"""R3.4 错题中心复习 HTTP:队列 + 提交评分 + 未登录 401。"""
import datetime as _dt
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d16_question_domain import WrongRecord

_TAG = "wcapi"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    token = r.json()["data"]["access_token"]
    async with _async_session_factory() as s:
        uid = (await s.execute(select(User.id).where(User.openid == openid))).scalar_one()
    return {"Authorization": f"Bearer {token}"}, uid


async def _cleanup(student):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.commit()


@pytest.mark.asyncio
async def test_review_queue_and_submit(client):
    headers, uid = await _login(client, f"{_TAG}_{uuid.uuid4().hex[:8]}")
    rid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(WrongRecord(id=rid, student_id=uid, q_scope="platform", question_id=uuid.uuid4(),
                           status="open", review_count=0, review_interval_days=1,
                           easiness_factor=Decimal("2.50"), next_review_at=_dt.date.today()))
        await db.commit()
    try:
        r = await client.get("/api/v1/wrong-center/review-queue", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["due_count"] >= 1 and any(it["id"] == str(rid) for it in data["items"])

        r = await client.post("/api/v1/wrong-center/review",
                              json={"wrong_record_id": str(rid), "quality": 5}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["review_count"] == 1
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.get("/api/v1/wrong-center/review-queue")
    assert r.status_code in (401, 403)
