"""运营 admin 仿真题审核发布流测试（M5 / D-095）。"""
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


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"adminq_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"adminq_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _seed_kp_with_draft_question() -> tuple[uuid.UUID, uuid.UUID]:
    """建 1 个 KP + 1 道 draft 仿真题，返回 (kp_id, question_id)。"""
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(),
            code=f"adminq-kp-{uuid.uuid4().hex[:6]}",
            name="审核测试 KP",
            category="grammar",
            description="m5 admin test",
            applicable_grades=["小学5年级"],
            applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        q = SimulatedQuestion(
            id=uuid.uuid4(),
            knowledge_point_id=kp.id,
            question_type="单选",
            stem="审核测试题：She ___ a teacher.",
            options=["A. is", "B. are", "C. am", "D. be"],
            answer="A",
            explanation="主语第三人称单数用 is。",
            difficulty=1,
            status="draft",
        )
        s.add(q)
        await s.commit()
        return kp.id, q.id


@pytest.mark.asyncio
async def test_admin_lists_draft_and_publishes(client):
    """运营能看到草稿题（含答案）、审核通过后学生端可见。"""
    kp_id, qid = await _seed_kp_with_draft_question()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])

    # 学生端此刻看不到（草稿）
    student_headers = await _login_as(client, f"stu_{uuid.uuid4().hex[:6]}")
    r0 = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions", headers=student_headers,
    )
    assert r0.status_code == 200
    assert len(r0.json()["data"]) == 0

    # 运营待审列表能看到这道草稿题，且含 answer
    r1 = await client.get(
        f"/api/v1/admin/questions?status=draft&kp_id={kp_id}", headers=admin_headers,
    )
    assert r1.status_code == 200
    data = r1.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(qid)
    assert data["items"][0]["answer"] == "A"
    assert data["items"][0]["status"] == "draft"

    # 审核通过 → published
    r2 = await client.post(
        f"/api/v1/admin/questions/{qid}/review", json={"approve": True}, headers=admin_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "published"

    # 学生端现在能看到了
    r3 = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions", headers=student_headers,
    )
    assert r3.status_code == 200
    items = r3.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == str(qid)
    assert "answer" not in items[0]  # 学生端不返回答案


@pytest.mark.asyncio
async def test_admin_reject_retires(client):
    """审核驳回 → retired，学生端依旧看不到。"""
    kp_id, qid = await _seed_kp_with_draft_question()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])

    r = await client.post(
        f"/api/v1/admin/questions/{qid}/review", json={"approve": False}, headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "retired"


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    """普通用户访问 admin 题库接口返回 403。"""
    headers = await _login_as(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/questions?status=draft", headers=headers)
    assert r.status_code == 403
