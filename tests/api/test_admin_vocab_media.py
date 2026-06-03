"""运营 admin 词力通图背单词媒体测试（P1 / D-101）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d5_learning import VocabularyWord


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"adminv_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"adminv_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _seed_word() -> uuid.UUID:
    async with _async_session_factory() as s:
        w = VocabularyWord(
            id=uuid.uuid4(), word=f"adminvocab_{uuid.uuid4().hex[:6]}", phonetic="t",
            definitions=[{"pos": "n.", "meaning": "测试"}], examples=None, difficulty=1,
        )
        s.add(w)
        await s.commit()
        return w.id


@pytest.mark.asyncio
async def test_admin_generate_edit_publish(client):
    """运营生成媒体 → 编辑英文描述 → 审核通过 → published。"""
    wid = await _seed_word()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])

    # 生成（dev-mock）→ draft + 5 类媒体
    r1 = await client.post(f"/api/v1/admin/vocab/{wid}/generate-media", headers=admin_headers)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()["data"]
    assert d1["media_status"] == "draft"
    assert d1["image_urls"] and len(d1["image_urls"]) >= 1
    assert d1["en_description"]
    assert d1["word_audio_url"] and d1["en_desc_audio_url"]

    # 待审列表能看到（用大 limit 避开存量草稿词分页）
    r2 = await client.get("/api/v1/admin/vocab?media_status=draft&limit=10000", headers=admin_headers)
    assert r2.status_code == 200
    assert any(it["word_id"] == str(wid) for it in r2.json()["data"]["items"])

    # 编辑英文描述
    r3 = await client.put(
        f"/api/v1/admin/vocab/{wid}/media",
        json={"en_description": "edited english desc"}, headers=admin_headers,
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["en_description"] == "edited english desc"

    # 审核通过 → published
    r4 = await client.post(
        f"/api/v1/admin/vocab/{wid}/media/review", json={"approve": True}, headers=admin_headers,
    )
    assert r4.status_code == 200
    assert r4.json()["data"]["media_status"] == "published"


@pytest.mark.asyncio
async def test_admin_reject_retires(client):
    wid = await _seed_word()
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])
    await client.post(f"/api/v1/admin/vocab/{wid}/generate-media", headers=admin_headers)
    r = await client.post(
        f"/api/v1/admin/vocab/{wid}/media/review", json={"approve": False}, headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["media_status"] == "retired"


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    headers = await _login_as(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/vocab?media_status=draft", headers=headers)
    assert r.status_code == 403
