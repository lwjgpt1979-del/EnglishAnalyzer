"""合规两项测试：年龄核验 + 协议确认 + 账号注销。"""
from app.schemas.compliance import (
    CURRENT_AGREEMENT_VERSION,
    CancelAccountConfirm,
    CompleteProfileRequest,
)


def test_agreement_version_defined():
    assert CURRENT_AGREEMENT_VERSION == "v1.0"


def test_complete_profile_request():
    req = CompleteProfileRequest(birth_year=2010, agreement_version="v1.0")
    assert req.birth_year == 2010
    assert req.guardian_phone is None


def test_cancel_account_confirm_validates_code_length():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CancelAccountConfirm(code="123")


# ── Service 测试 ──────────────────────────────────────────────────────────────
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services.auth_service import (
    upsert_user,
    complete_profile,
    guardian_verify,
    compute_age,
)
from app.services.cancellation_service import (
    request_cancellation,
    confirm_cancellation,
    revoke_cancellation,
    execute_cancellation_if_due,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def new_user(db_session):
    user = await upsert_user(db_session, openid=f"cmp_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


def test_compute_age():
    assert compute_age(2010) == datetime.now(timezone.utc).year - 2010


@pytest.mark.asyncio
async def test_complete_profile_adult(db_session, new_user):
    res = await complete_profile(
        db_session, user=new_user, birth_year=1990, guardian_phone=None,
        user_phone="13800001111", agreement_version="v1.0",
    )
    assert res.profile_completed is True
    assert res.needs_guardian_verify is False


@pytest.mark.asyncio
async def test_complete_profile_minor_requires_guardian(db_session, new_user):
    with pytest.raises(AppError) as exc:
        await complete_profile(
            db_session, user=new_user, birth_year=2020, guardian_phone=None,
            user_phone=None, agreement_version="v1.0",
        )
    assert exc.value.code == 400


@pytest.mark.asyncio
async def test_complete_profile_minor_with_guardian(db_session, new_user):
    res = await complete_profile(
        db_session, user=new_user, birth_year=2020, guardian_phone="13800001234",
        user_phone=None, agreement_version="v1.0",
    )
    assert res.needs_guardian_verify is True
    assert new_user.profile_completed is False
    assert new_user.guardian_phone == "13800001234"


@pytest.mark.asyncio
async def test_guardian_verify_success(db_session, new_user):
    await complete_profile(
        db_session, user=new_user, birth_year=2020, guardian_phone="13800001234",
        user_phone=None, agreement_version="v1.0",
    )
    from app.services.sms_service import DEV_FIXED_CODE, expires_at_from_now
    # dev mode 已直接把 DEV_FIXED_CODE 写到 user.phone_verify_code（complete_profile 内部）；这里只需验证
    await guardian_verify(db_session, user=new_user, code=DEV_FIXED_CODE)
    assert new_user.profile_completed is True
    assert new_user.guardian_verified_at is not None


@pytest.mark.asyncio
async def test_request_and_confirm_cancellation(db_session, new_user):
    new_user.phone = "13800009999"
    await db_session.flush()

    await request_cancellation(db_session, user=new_user)
    assert new_user.phone_verify_code is not None

    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)
    assert new_user.deactivation_requested_at is not None
    assert new_user.deactivation_scheduled_at is not None
    assert new_user.is_active is False


@pytest.mark.asyncio
async def test_revoke_cancellation(db_session, new_user):
    new_user.phone = "13800009999"
    await db_session.flush()
    await request_cancellation(db_session, user=new_user)
    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)

    await revoke_cancellation(db_session, user=new_user)
    assert new_user.deactivation_requested_at is None
    assert new_user.is_active is True


@pytest.mark.asyncio
async def test_execute_cancellation_if_due_anonymizes(db_session, new_user):
    new_user.phone = "13800009999"
    new_user.nickname = "Original"
    await db_session.flush()
    await request_cancellation(db_session, user=new_user)
    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)

    new_user.deactivation_scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    await execute_cancellation_if_due(db_session, user=new_user)
    assert new_user.is_anonymized is True
    assert new_user.nickname is None
    assert new_user.phone is None
    assert new_user.openid.startswith("deleted_")


# ── API 测试 ──────────────────────────────────────────────────────────────────
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, openid_suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"cmp_api_{openid_suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_complete_profile_api_adult(client):
    headers = await _login(client, f"adult_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0", "user_phone": "13800001111"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["profile_completed"] is True


@pytest.mark.asyncio
async def test_complete_profile_api_minor(client):
    headers = await _login(client, f"minor_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 2020, "guardian_phone": "13800002222", "agreement_version": "v1.0"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["needs_guardian_verify"] is True
    assert resp.json()["data"]["profile_completed"] is False


@pytest.mark.asyncio
async def test_cancel_account_full_flow(client):
    headers = await _login(client, f"cancel_{uuid.uuid4().hex[:6]}")
    # 先完善 profile 拿到 phone
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0", "user_phone": "13900009999"},
        headers=headers,
    )
    # 申请
    r1 = await client.post("/api/v1/auth/cancel-account/request", headers=headers)
    assert r1.status_code == 200
    # 确认（dev 固定码 123456）
    r2 = await client.post(
        "/api/v1/auth/cancel-account/confirm",
        json={"code": "123456"}, headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["days_remaining"] is not None
    # 撤销
    r3 = await client.post("/api/v1/auth/cancel-account/revoke", headers=headers)
    assert r3.status_code == 200
