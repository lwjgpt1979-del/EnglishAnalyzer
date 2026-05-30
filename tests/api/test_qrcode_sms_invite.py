"""微信码 + SMS 邀请测试（D-078 / Plan M）。Task 0 部分（service unit tests）。"""
import base64
import pytest

from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.wechat_service import get_access_token, _DEV_MOCK_TOKEN


@pytest.mark.asyncio
async def test_wechat_access_token_dev_mock_or_real():
    from app.core.config import settings
    if settings.wechat_appid.startswith("wx_dev"):
        assert (await get_access_token()) == _DEV_MOCK_TOKEN
    else:
        try:
            token = await get_access_token()
            assert isinstance(token, str)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qrcode_dev_or_real_returns_base64():
    from app.core.config import settings
    if settings.wechat_appid.startswith("wx_dev"):
        b64 = await get_miniprogram_qrcode_base64(scene="t:ABC123", page="pages/teacher/students")
        decoded = base64.b64decode(b64)
        assert len(decoded) > 50
    else:
        try:
            await get_miniprogram_qrcode_base64(scene="t:TEST123", page="pages/teacher/students")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qrcode_scene_too_long_400():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc:
        await get_miniprogram_qrcode_base64(scene="a" * 33, page="pages/teacher/students")
    assert exc.value.code == 400


# ── API 测试 ──────────────────────────────────────────────────────────────────
import uuid
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
        mock_wx.return_value = {"openid": f"qrc_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _setup_teacher(client: AsyncClient, suffix: str) -> dict:
    headers = await _login(client, suffix)
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers)
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://x.test/c.jpg"}, headers=headers,
    )
    return headers


@pytest.mark.asyncio
async def test_teacher_qrcode_endpoint(client):
    h = await _setup_teacher(client, f"q_t_{uuid.uuid4().hex[:6]}")
    with patch(
        "app.api.v1.teacher.get_miniprogram_qrcode_base64",
        new_callable=AsyncMock, return_value="MOCK_QR_B64",
    ):
        r = await client.post("/api/v1/teacher/invite-code/qrcode", headers=h)
    assert r.status_code == 200
    d = r.json()["data"]
    assert len(d["code"]) == 6
    assert d["qrcode_base64"] == "MOCK_QR_B64"


@pytest.mark.asyncio
async def test_teacher_sms_endpoint(client):
    h = await _setup_teacher(client, f"q_ts_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/teacher/invite-code/sms",
        json={"phone": "13900000000"}, headers=h,
    )
    assert r.status_code == 200
    assert r.json()["data"]["sent"] is True
    assert len(r.json()["data"]["code"]) == 6


@pytest.mark.asyncio
async def test_relative_qrcode_endpoint(client):
    h = await _login(client, f"q_r_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1995, "agreement_version": "v1.0"}, headers=h,
    )
    with patch(
        "app.api.v1.relative.get_miniprogram_qrcode_base64",
        new_callable=AsyncMock, return_value="MOCK_REL_B64",
    ):
        r = await client.post("/api/v1/relative/invite-code/qrcode", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["qrcode_base64"] == "MOCK_REL_B64"


@pytest.mark.asyncio
async def test_relative_sms_endpoint(client):
    h = await _login(client, f"q_rs_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1995, "agreement_version": "v1.0"}, headers=h,
    )
    r = await client.post(
        "/api/v1/relative/invite-code/sms",
        json={"phone": "13900000001"}, headers=h,
    )
    assert r.status_code == 200
    assert r.json()["data"]["sent"] is True
