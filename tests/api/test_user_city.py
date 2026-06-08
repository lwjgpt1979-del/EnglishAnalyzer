"""V2 M27 — 用户城市归属测试。"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


@pytest_asyncio.fixture
async def student_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as m:
        m.return_value = {"openid": f"m27stu_{uuid.uuid4().hex[:8]}"}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_can_update_city_via_patch(client: AsyncClient, student_headers):
    """PATCH /auth/profile city_code 写入 users.city_code，city_source=self_selected。"""
    r = await client.patch(
        "/api/v1/auth/profile",
        json={"city_code": "4401"},
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["city_code"] == "4401"


@pytest.mark.asyncio
async def test_city_persists_across_requests(client: AsyncClient, student_headers):
    """城市保存后再次调用 PATCH 不覆盖（只传其他字段时）。"""
    # 先设置城市
    await client.patch("/api/v1/auth/profile", json={"city_code": "3101"}, headers=student_headers)
    # 只更新教材偏好，city_code 不传
    r = await client.patch(
        "/api/v1/auth/profile",
        json={"preferred_grade": "小学6年级"},
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    # city_code 应该还在（返回值包含 city_code）
    data = r.json()["data"]
    assert data["city_code"] == "3101"
