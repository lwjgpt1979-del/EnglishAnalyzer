"""V2 M23 — 用户修改教材偏好测试。"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


@pytest_asyncio.fixture
async def student_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"m23_stu_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_can_update_preferred_textbook(client: AsyncClient, student_headers):
    """PATCH /auth/profile 可更新三个教材偏好字段。"""
    r = await client.patch(
        "/api/v1/auth/profile",
        json={
            "preferred_textbook_version": "人教版",
            "preferred_grade": "初中7年级",
            "preferred_semester": "下",
        },
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data") or {}
    assert data["preferred_textbook_version"] == "人教版"
    assert data["preferred_grade"] == "初中7年级"
    assert data["preferred_semester"] == "下"


@pytest.mark.asyncio
async def test_partial_update_preserves_other_fields(client: AsyncClient, student_headers):
    """只传一个字段时，其余字段不变。"""
    # 先设置完整值
    await client.patch(
        "/api/v1/auth/profile",
        json={"preferred_textbook_version": "译林版", "preferred_grade": "小学5年级", "preferred_semester": "上"},
        headers=student_headers,
    )
    # 只修改年级
    r = await client.patch(
        "/api/v1/auth/profile",
        json={"preferred_grade": "小学6年级"},
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json().get("data") or {}
    assert data["preferred_textbook_version"] == "译林版"
    assert data["preferred_grade"] == "小学6年级"
    assert data["preferred_semester"] == "上"
