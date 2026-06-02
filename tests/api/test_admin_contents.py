"""运营 admin 知识点内容审核/编辑测试（M5 / D-096）。"""
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
from app.models.d11_v2_curriculum import KnowledgePointContent


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"adminc_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"adminc_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _seed_draft_content() -> tuple[uuid.UUID, uuid.UUID]:
    """建 1 个 KP + 1 条 draft 内容，返回 (kp_id, content_id)。"""
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(), code=f"adminc-kp-{uuid.uuid4().hex[:6]}", name="内容审核KP",
            category="grammar", description="m5 admin content test",
            applicable_grades=["小学5年级"], applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        c = KnowledgePointContent(
            id=uuid.uuid4(), knowledge_point_id=kp.id, dimension="grammar",
            content_md="待审草稿正文", status="draft", generated_by="ai_full",
        )
        s.add(c)
        await s.commit()
        return kp.id, c.id


@pytest.mark.asyncio
async def test_admin_lists_edits_and_publishes(client):
    """运营看到草稿内容 → 编辑正文 → 审核通过 → published。"""
    kp_id, cid = await _seed_draft_content()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])

    # 待审列表能看到这条草稿
    r1 = await client.get(
        f"/api/v1/admin/contents?status=draft&kp_id={kp_id}", headers=admin_headers,
    )
    assert r1.status_code == 200
    data = r1.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(cid)
    assert data["items"][0]["content_md"] == "待审草稿正文"
    assert data["items"][0]["status"] == "draft"

    # 编辑正文 → generated_by 变 ai_with_human_review
    r2 = await client.put(
        f"/api/v1/admin/contents/{cid}", json={"content_md": "运营修订后的正文"},
        headers=admin_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["content_md"] == "运营修订后的正文"
    assert r2.json()["data"]["generated_by"] == "ai_with_human_review"

    # 审核通过 → published
    r3 = await client.post(
        f"/api/v1/admin/contents/{cid}/review", json={"approve": True},
        headers=admin_headers,
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_admin_reject_retires(client):
    """审核驳回 → retired。"""
    _, cid = await _seed_draft_content()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])
    r = await client.post(
        f"/api/v1/admin/contents/{cid}/review", json={"approve": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "retired"


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    """普通用户访问 admin 内容接口返回 403。"""
    headers = await _login_as(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/contents?status=draft", headers=headers)
    assert r.status_code == 403
