"""运营数据大盘 overview 测试（M5 / D-099）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.services import admin_auth_service, admin_stats_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"ov_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"ov_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


@pytest.mark.asyncio
async def test_overview_counts_draft_delta(db_session):
    """新增 2 道 draft 题后，draft 计数 +2；四状态键齐全。"""
    before = await admin_stats_service.get_overview(db_session)
    kp = KnowledgePoint(
        id=uuid.uuid4(), code=f"ov-{uuid.uuid4().hex[:6]}", name="overviewKP",
        category="grammar", description="d",
        applicable_grades=["小学5年级"], applicable_textbooks=["译林版"],
    )
    db_session.add(kp)
    await db_session.flush()
    for i in range(2):
        db_session.add(SimulatedQuestion(
            id=uuid.uuid4(), knowledge_point_id=kp.id, question_type="单选",
            stem=f"overview q{i}", options=["A", "B"], answer="A",
            explanation="x", difficulty=1, status="draft",
        ))
    await db_session.flush()
    after = await admin_stats_service.get_overview(db_session)
    assert set(after.questions_by_status.keys()) == {"draft", "reviewing", "published", "retired"}
    assert after.questions_by_status["draft"] == before.questions_by_status["draft"] + 2
    assert after.total_users >= before.total_users


@pytest.mark.asyncio
async def test_overview_api(client):
    headers = await _make_admin(client, uuid.uuid4().hex[:6])
    r = await client.get("/api/v1/admin/overview", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "questions_by_status" in data
    assert "contents_by_status" in data
    assert "total_users" in data and "paid_orders" in data
    assert set(data["questions_by_status"].keys()) == {"draft", "reviewing", "published", "retired"}


@pytest.mark.asyncio
async def test_overview_non_admin_403(client):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"ovplain_{uuid.uuid4().hex[:6]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    r = await client.get("/api/v1/admin/overview", headers=headers)
    assert r.status_code == 403
