"""
V2 M9: 诊断报告 GET /api/v1/diagnosis/ 返回
question_type_distribution、difficulty_distribution、mastered_count 字段。
TDD RED: import 失败（DB 未连接）→ GREEN: 字段断言通过。
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _auth(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"diag_dist_{suffix}"}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    assert r.status_code == 200
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_diagnosis_report_has_distribution_fields(client):
    """诊断报告响应必须包含 question_type_distribution / difficulty_distribution / mastered_count。"""
    import uuid
    tag = uuid.uuid4().hex[:6]
    headers = await _auth(client, tag)

    # 完善 profile（成人用户）
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1998, "agreement_version": "v1.0"},
        headers=headers,
    )

    resp = await client.get("/api/v1/diagnosis/", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # 三个字段必须存在
    assert "question_type_distribution" in data, "缺少 question_type_distribution 字段"
    assert "difficulty_distribution" in data, "缺少 difficulty_distribution 字段"
    assert "mastered_count" in data, "缺少 mastered_count 字段"

    # 类型检查
    assert isinstance(data["question_type_distribution"], dict)
    assert isinstance(data["difficulty_distribution"], dict)
    assert isinstance(data["mastered_count"], int)
