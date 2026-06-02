"""运营 admin 学期定价配置测试（M5 / D-097）。"""
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


async def _login_as(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"adminp_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"adminp_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _cleanup_pricing_config() -> None:
    """删除提交的 semester_pricing 行，恢复"无配置→默认"状态，避免污染依赖默认价的测试。"""
    from app.models.d9_system import SystemConfig
    async with _async_session_factory() as s:
        cfg = (await s.execute(
            select(SystemConfig).where(SystemConfig.key == "semester_pricing")
        )).scalar_one_or_none()
        if cfg is not None:
            await s.delete(cfg)
            await s.commit()


@pytest.mark.asyncio
async def test_admin_get_and_update_pricing(client):
    """运营 PUT 改定价 → GET 读到新值。"""
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])
    try:
        r1 = await client.put(
            "/api/v1/admin/pricing", json={"basic": 59, "pro": 99, "promax": 199},
            headers=admin_headers,
        )
        assert r1.status_code == 200
        assert r1.json()["data"] == {"basic": 59, "pro": 99, "promax": 199}

        r2 = await client.get("/api/v1/admin/pricing", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["data"] == {"basic": 59, "pro": 99, "promax": 199}
    finally:
        await _cleanup_pricing_config()


@pytest.mark.asyncio
async def test_update_pricing_rejects_non_positive(client):
    """非正单价被 422 拒绝。"""
    admin_headers = await _make_admin(client, uuid.uuid4().hex[:6])
    r = await client.put(
        "/api/v1/admin/pricing", json={"basic": 0, "pro": 99, "promax": 199},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    """普通用户访问 admin 定价接口返回 403。"""
    headers = await _login_as(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/pricing", headers=headers)
    assert r.status_code == 403
