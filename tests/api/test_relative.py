"""亲人端测试（D-076）。"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import _async_session_factory
from app.models.d1_users import User


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"rel_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _setup_user(client: AsyncClient, suffix: str, birth_year: int = 1990) -> tuple[dict, str]:
    """注册一个用户并完善 profile。返回 (headers, user_id)。"""
    headers = await _login(client, suffix)
    if birth_year > 2010:  # 14岁以下需要 guardian 流程
        await client.post(
            "/api/v1/auth/complete-profile",
            json={"birth_year": birth_year, "guardian_phone": "13800001234", "agreement_version": "v1.0"},
            headers=headers,
        )
        await client.post("/api/v1/auth/guardian-verify", json={"code": "123456"}, headers=headers)
    else:
        await client.post(
            "/api/v1/auth/complete-profile",
            json={"birth_year": birth_year, "agreement_version": "v1.0"},
            headers=headers,
        )
    async with _async_session_factory() as s:
        user = (await s.execute(select(User).where(User.openid == f"rel_{suffix}"))).scalar_one()
        return headers, str(user.id)


@pytest.mark.asyncio
async def test_generate_invite_code(client):
    s_h, _ = await _setup_user(client, f"gen_{uuid.uuid4().hex[:6]}", 2010)
    r = await client.post("/api/v1/relative/invite-code", headers=s_h)
    assert r.status_code == 200
    assert len(r.json()["data"]["code"]) == 6


@pytest.mark.asyncio
async def test_full_bind_flow(client):
    s_h, sid = await _setup_user(client, f"bs_{uuid.uuid4().hex[:6]}", 2010)
    p_h, pid = await _setup_user(client, f"bp_{uuid.uuid4().hex[:6]}", 1985)

    iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
    code = iv.json()["data"]["code"]
    r = await client.post(
        "/api/v1/relative/bind",
        json={"code": code, "relationship": "母亲"}, headers=p_h,
    )
    assert r.status_code == 200
    assert r.json()["data"]["relationship"] == "母亲"
    assert r.json()["data"]["student_id"] == sid

    r2 = await client.get("/api/v1/relative/students", headers=p_h)
    assert r2.json()["data"][0]["student_id"] == sid

    r3 = await client.get("/api/v1/relative/my-relatives", headers=s_h)
    assert any(item["student_id"] == pid for item in r3.json()["data"])


@pytest.mark.asyncio
async def test_invalid_code_400(client):
    p_h, _ = await _setup_user(client, f"bad_{uuid.uuid4().hex[:6]}", 1985)
    r = await client.post(
        "/api/v1/relative/bind",
        json={"code": "XXXXXX", "relationship": "父亲"}, headers=p_h,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_bind_409(client):
    s_h, _ = await _setup_user(client, f"ds_{uuid.uuid4().hex[:6]}", 2010)
    p_h, _ = await _setup_user(client, f"dp_{uuid.uuid4().hex[:6]}", 1985)

    iv1 = await client.post("/api/v1/relative/invite-code", headers=s_h)
    await client.post(
        "/api/v1/relative/bind",
        json={"code": iv1.json()["data"]["code"], "relationship": "母亲"}, headers=p_h,
    )
    iv2 = await client.post("/api/v1/relative/invite-code", headers=s_h)
    r = await client.post(
        "/api/v1/relative/bind",
        json={"code": iv2.json()["data"]["code"], "relationship": "母亲"}, headers=p_h,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_max_4_limit(client):
    s_h, _ = await _setup_user(client, f"ms_{uuid.uuid4().hex[:6]}", 2010)
    for i in range(4):
        p_h, _ = await _setup_user(client, f"mp{i}_{uuid.uuid4().hex[:6]}", 1985)
        iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
        r = await client.post(
            "/api/v1/relative/bind",
            json={"code": iv.json()["data"]["code"], "relationship": f"亲人{i}"}, headers=p_h,
        )
        assert r.status_code == 200
    # 第 5 个失败
    p5_h, _ = await _setup_user(client, f"mp5_{uuid.uuid4().hex[:6]}", 1985)
    iv5 = await client.post("/api/v1/relative/invite-code", headers=s_h)
    r5 = await client.post(
        "/api/v1/relative/bind",
        json={"code": iv5.json()["data"]["code"], "relationship": "第五个"}, headers=p5_h,
    )
    assert r5.status_code == 400


@pytest.mark.asyncio
async def test_unbind_relative(client):
    s_h, _ = await _setup_user(client, f"us_{uuid.uuid4().hex[:6]}", 2010)
    p_h, pid = await _setup_user(client, f"up_{uuid.uuid4().hex[:6]}", 1985)

    iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
    await client.post(
        "/api/v1/relative/bind",
        json={"code": iv.json()["data"]["code"], "relationship": "母亲"}, headers=p_h,
    )

    r = await client.delete(f"/api/v1/relative/relatives/{pid}", headers=s_h)
    assert r.status_code == 200
    r2 = await client.get("/api/v1/relative/my-relatives", headers=s_h)
    assert all(item["student_id"] != pid for item in r2.json()["data"])


@pytest.mark.asyncio
async def test_relative_view_student_diagnosis(client):
    s_h, sid = await _setup_user(client, f"vd_s_{uuid.uuid4().hex[:6]}", 2010)
    p_h, _ = await _setup_user(client, f"vd_p_{uuid.uuid4().hex[:6]}", 1985)

    iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
    await client.post(
        "/api/v1/relative/bind",
        json={"code": iv.json()["data"]["code"], "relationship": "父亲"}, headers=p_h,
    )

    r = await client.get(f"/api/v1/relative/students/{sid}/diagnosis-report", headers=p_h)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "total_questions" in d
    assert "mastery_rate" in d


@pytest.mark.asyncio
async def test_relative_view_unbound_student_403(client):
    p_h, _ = await _setup_user(client, f"vd_ub_{uuid.uuid4().hex[:6]}", 1985)
    rnd_sid = uuid.uuid4()
    r = await client.get(
        f"/api/v1/relative/students/{rnd_sid}/diagnosis-report", headers=p_h,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_relative_pays_for_student(client):
    """亲人代付：order 创建 + 14-17 minor_consent 自动写入。"""
    s_h, sid = await _setup_user(client, f"pay_s_{uuid.uuid4().hex[:6]}", 2012)  # 14岁
    p_h, _ = await _setup_user(client, f"pay_p_{uuid.uuid4().hex[:6]}", 1985)

    iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
    await client.post(
        "/api/v1/relative/bind",
        json={"code": iv.json()["data"]["code"], "relationship": "母亲"}, headers=p_h,
    )

    r = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "basic", "duration_months": 1, "order_type": "new",
            "target_student_id": sid,
        },
        headers=p_h,
    )
    assert r.status_code == 200
    assert "id" in r.json()["data"]
    # 14-17 岁 minor_purchase_consent_at 应已写入
    async with _async_session_factory() as s:
        student = (await s.execute(
            select(User).where(User.id == uuid.UUID(sid))
        )).scalar_one()
        assert student.minor_purchase_consent_at is not None


@pytest.mark.asyncio
async def test_pay_for_unbound_student_403(client):
    p_h, _ = await _setup_user(client, f"upay_p_{uuid.uuid4().hex[:6]}", 1985)
    rnd_sid = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "basic", "duration_months": 1, "order_type": "new",
            "target_student_id": rnd_sid,
        },
        headers=p_h,
    )
    assert r.status_code == 403
