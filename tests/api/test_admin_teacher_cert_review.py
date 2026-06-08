"""Admin 教师认证审核 TDD 测试（V2 M7）。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User, Teacher


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


# ── 工具：登录 + 提权 ────────────────────────────────────────────────────────

async def _login(client: AsyncClient, openid: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin_headers(client: AsyncClient) -> dict:
    oid = f"admin_tcert_{uuid.uuid4().hex[:8]}"
    headers = await _login(client, oid)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == oid))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _seed_pending_teacher() -> uuid.UUID:
    """植入一名 pending 认证状态的老师，返回 user_id。"""
    async with _async_session_factory() as s:
        uid = uuid.uuid4()
        user = User(
            id=uid,
            openid=f"teacher_pending_{uid.hex[:8]}",
            role="teacher",  # type: ignore[arg-type]
        )
        teacher = Teacher(
            id=uid,
            subject="英语",
            cert_status="pending",  # type: ignore[arg-type]
            cert_doc_url="https://example.com/cert.jpg",
            max_students=30,
        )
        s.add(user)
        await s.flush()  # must persist user before teacher (FK: teachers.id → users.id)
        s.add(teacher)
        await s.commit()
    return uid


# ── 测试 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_teachers_requires_admin(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/admin/teachers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_all_teachers(client: AsyncClient):
    """Admin 鉴权 → 200，返回 items/total 结构。"""
    headers = await _make_admin_headers(client)
    r = await client.get("/api/v1/admin/teachers", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data and "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_filter_by_cert_status_pending(client: AsyncClient):
    """植入 pending 老师 → cert_status=pending 筛选后能找到该老师。"""
    teacher_id = await _seed_pending_teacher()
    headers = await _make_admin_headers(client)
    r = await client.get("/api/v1/admin/teachers?cert_status=pending&limit=200", headers=headers)
    assert r.status_code == 200
    ids = [item["teacher_id"] for item in r.json()["data"]["items"]]
    assert str(teacher_id) in ids


@pytest.mark.asyncio
async def test_review_teacher_approve(client: AsyncClient):
    """approve=True → cert_status 变为 'certified'。"""
    teacher_id = await _seed_pending_teacher()
    headers = await _make_admin_headers(client)
    r = await client.post(
        f"/api/v1/admin/teachers/{teacher_id}/review",
        json={"approve": True},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["cert_status"] == "certified"


@pytest.mark.asyncio
async def test_review_teacher_reject(client: AsyncClient):
    """approve=False → cert_status 变为 'rejected'。"""
    teacher_id = await _seed_pending_teacher()
    headers = await _make_admin_headers(client)
    r = await client.post(
        f"/api/v1/admin/teachers/{teacher_id}/review",
        json={"approve": False, "reason": "材料不清晰"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["cert_status"] == "rejected"


@pytest.mark.asyncio
async def test_overview_has_pending_teachers(client: AsyncClient):
    """数据大盘 /admin/overview 含 pending_teachers 字段且 ≥ 0。"""
    await _seed_pending_teacher()
    headers = await _make_admin_headers(client)
    r = await client.get("/api/v1/admin/overview", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "pending_teachers" in data, f"缺少 pending_teachers 字段，实际: {data.keys()}"
    assert data["pending_teachers"] >= 1
