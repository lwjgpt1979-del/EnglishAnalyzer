"""运营 admin 作文模板配置测试（D-111）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"admine_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"admine_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _cleanup() -> None:
    from app.models.d9_system import SystemConfig
    async with _async_session_factory() as s:
        cfg = (await s.execute(
            select(SystemConfig).where(SystemConfig.key == "essay_templates")
        )).scalar_one_or_none()
        if cfg is not None:
            await s.delete(cfg)
            await s.commit()


@pytest.mark.asyncio
async def test_admin_get_update_essay_templates(client):
    headers = await _make_admin(client, uuid.uuid4().hex[:6])
    try:
        r0 = await client.get("/api/v1/admin/essay-templates", headers=headers)
        assert r0.status_code == 200 and "_default" in r0.json()["data"]
        payload = {"话题作文": {"template": "运营模板", "samples": ["a", "b", "c"]},
                   "_default": {"template": "兜底", "samples": ["d"]}}
        r1 = await client.put("/api/v1/admin/essay-templates", json=payload, headers=headers)
        assert r1.status_code == 200
        r2 = await client.get("/api/v1/admin/essay-templates", headers=headers)
        assert r2.json()["data"]["话题作文"]["template"] == "运营模板"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_admin_templates_requires_admin(client):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"normal_{uuid.uuid4().hex[:6]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    r = await client.get("/api/v1/admin/essay-templates", headers=headers)
    assert r.status_code in (401, 403)
