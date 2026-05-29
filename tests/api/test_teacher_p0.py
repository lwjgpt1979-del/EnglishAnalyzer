"""老师端 P0 三项测试（D-075）：cert + diagnosis + class。"""
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


async def _login_as(client: AsyncClient, openid_suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"t_p0_{openid_suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_teacher(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers)
    return headers


@pytest.mark.asyncio
async def test_cert_submit_auto_approves_in_dev(client):
    headers = await _make_teacher(client, f"cert_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.example.com/cert.jpg"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["cert_status"] == "certified"
    assert r.json()["data"]["cert_doc_url"] == "https://cdn.example.com/cert.jpg"


@pytest.mark.asyncio
async def test_unverified_teacher_cannot_invite(client):
    from app.core.config import settings
    original = settings.auto_approve_teacher_cert
    settings.auto_approve_teacher_cert = False
    try:
        headers = await _make_teacher(client, f"unverif_{uuid.uuid4().hex[:6]}")
        r = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r.status_code == 403
        await client.post(
            "/api/v1/teacher/cert/submit",
            json={"cert_doc_url": "https://cdn.example.com/c.jpg"}, headers=headers,
        )
        r2 = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r2.status_code == 403  # pending 仍未通过
    finally:
        settings.auto_approve_teacher_cert = original


@pytest.mark.asyncio
async def test_admin_review_certifies_teacher(client):
    from app.core.config import settings
    original = settings.auto_approve_teacher_cert
    settings.auto_approve_teacher_cert = False
    try:
        t_suffix = f"adm_t_{uuid.uuid4().hex[:6]}"
        headers = await _make_teacher(client, t_suffix)
        await client.post(
            "/api/v1/teacher/cert/submit",
            json={"cert_doc_url": "https://cdn.example.com/c.jpg"}, headers=headers,
        )
        async with _async_session_factory() as s:
            user = (await s.execute(
                select(User).where(User.openid == f"t_p0_{t_suffix}")
            )).scalar_one()
            tid = user.id

        admin_suffix = f"admin_{uuid.uuid4().hex[:6]}"
        admin_headers = await _login_as(client, admin_suffix)
        async with _async_session_factory() as s:
            admin = (await s.execute(
                select(User).where(User.openid == f"t_p0_{admin_suffix}")
            )).scalar_one()
            admin.role = "platform_admin"  # type: ignore[assignment]
            await s.commit()

        r = await client.post(
            f"/api/v1/admin/teachers/{tid}/review",
            json={"approve": True}, headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["cert_status"] == "certified"

        r2 = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r2.status_code == 200
    finally:
        settings.auto_approve_teacher_cert = original


@pytest.mark.asyncio
async def test_teacher_view_student_diagnosis(client):
    """老师通过绑定关系查看学生学情报告。"""
    t_headers = await _make_teacher(client, f"diag_t_{uuid.uuid4().hex[:6]}")
    # cert auto-approve（dev 默认）但还是显式提交一次确保 certified
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )

    s_suffix = f"diag_s_{uuid.uuid4().hex[:6]}"
    s_headers = await _login_as(client, s_suffix)
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 2010, "guardian_phone": "13800001234", "agreement_version": "v1.0"},
        headers=s_headers,
    )
    await client.post("/api/v1/auth/guardian-verify", json={"code": "123456"}, headers=s_headers)

    iv = await client.post("/api/v1/teacher/invite-code", headers=t_headers)
    code = iv.json()["data"]["code"]
    await client.post("/api/v1/teacher/bind", json={"code": code}, headers=s_headers)

    async with _async_session_factory() as s:
        stu = (await s.execute(
            select(User).where(User.openid == f"t_p0_{s_suffix}")
        )).scalar_one()
        sid = stu.id

    r = await client.get(f"/api/v1/teacher/students/{sid}/diagnosis-report", headers=t_headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "total_questions" in d
    assert "mastery_rate" in d
    assert "top_error_types" in d


@pytest.mark.asyncio
async def test_teacher_view_unbound_student_403(client):
    t_headers = await _make_teacher(client, f"diag_ub_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )
    rnd_sid = uuid.uuid4()
    r = await client.get(f"/api/v1/teacher/students/{rnd_sid}/diagnosis-report", headers=t_headers)
    assert r.status_code == 403
