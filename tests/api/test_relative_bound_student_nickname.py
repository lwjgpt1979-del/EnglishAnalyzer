"""
V2 M11: GET /relative/students 返回的 BoundStudentOut 包含 nickname 字段。
TDD RED → GREEN。
"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_bound_student_list_includes_nickname(client):
    """家人查学生列表：每条记录应包含 nickname 字段（可为 null）。"""
    tag = uuid.uuid4().hex[:6]

    # 学生账号
    s_h = await _login(client, f"nick_stu_{tag}")
    await client.post("/api/v1/auth/complete-profile",
                      json={"birth_year": 2010, "agreement_version": "v1.0"}, headers=s_h)

    # 家人账号
    r_h = await _login(client, f"nick_rel_{tag}")
    await client.post("/api/v1/auth/complete-profile",
                      json={"birth_year": 1980, "agreement_version": "v1.0"}, headers=r_h)

    # 学生生成邀请码
    code_r = await client.post("/api/v1/relative/invite-codes/generate", headers=s_h)
    assert code_r.status_code == 200
    code = code_r.json()["data"]["code"]

    # 家人绑定
    bind_r = await client.post("/api/v1/relative/bind", json={"invite_code": code}, headers=r_h)
    assert bind_r.status_code == 200

    # 家人查列表
    list_r = await client.get("/api/v1/relative/students", headers=r_h)
    assert list_r.status_code == 200
    items = list_r.json()["data"]
    assert len(items) >= 1

    item = items[0]
    assert "nickname" in item, "BoundStudentOut 缺少 nickname 字段"
    # nickname 可为 null（学生还没设置）或字符串
    assert item["nickname"] is None or isinstance(item["nickname"], str)
