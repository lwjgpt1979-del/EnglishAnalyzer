"""
V2 M8: 家人代付使用 V2 学期模式下单（非 V1 duration_months）。
TDD RED: 先 import，DB 连不上时 ImportError → RED；连接成功后走真实路径 GREEN。
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


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"relord_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_relative_can_create_v2_semester_order_for_student(client):
    """家人可以用 semesters 参数给学生下 V2 学期订单（不传 duration_months）。"""
    tag = uuid.uuid4().hex[:6]

    # 创建学生账号
    s_headers = await _login(client, f"stu_{tag}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 2012, "agreement_version": "v1.0"},
        headers=s_headers,
    )
    me_resp = await client.get("/api/v1/users/me", headers=s_headers)
    assert me_resp.status_code == 200
    student_id = me_resp.json()["data"]["id"]

    # 创建家人账号并绑定学生
    r_headers = await _login(client, f"rel_{tag}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1985, "agreement_version": "v1.0"},
        headers=r_headers,
    )

    # 生成邀请码并绑定
    code_resp = await client.post("/api/v1/relative/invite-codes/generate", headers=s_headers)
    assert code_resp.status_code == 200
    code = code_resp.json()["data"]["code"]
    bind_resp = await client.post(
        "/api/v1/relative/bind", json={"invite_code": code}, headers=r_headers
    )
    assert bind_resp.status_code == 200

    # 家人用 V2 semesters 参数代付下单
    order_resp = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "basic",
            "order_type": "new",
            "semesters": [
                {
                    "textbook_version": "译林版",
                    "grade": "小学5年级",
                    "semester": "上",
                }
            ],
            "target_student_id": student_id,
        },
        headers=r_headers,
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()["data"]
    assert order["amount"] == 39  # basic 学期价 ¥39
    assert order["status"] in ("pending", "paid")


@pytest.mark.asyncio
async def test_v2_semester_order_no_duration_months(client):
    """V2 学期订单不需要也不应依赖 duration_months 字段。"""
    tag = uuid.uuid4().hex[:6]
    headers = await _login(client, f"solo_{tag}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1995, "agreement_version": "v1.0"},
        headers=headers,
    )

    # 只传 semesters，不传 duration_months
    resp = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "pro",
            "order_type": "new",
            "semesters": [
                {
                    "textbook_version": "人教版",
                    "grade": "初中7年级",
                    "semester": "下",
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["amount"] == 79  # pro 学期价 ¥79
