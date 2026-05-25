import time
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from jose import JWTError
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import _async_session_factory, get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.base import BaseResponse, make_ok, make_error
from app.services.auth_service import upsert_user
from sqlalchemy.ext.asyncio import AsyncSession


def test_settings_loads_database_url():
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_loads_async_database_url():
    assert settings.async_database_url.startswith("postgresql+psycopg_async://")


def test_settings_has_jwt_secret():
    assert len(settings.jwt_secret_key) >= 8


def test_make_ok_structure():
    resp = make_ok({"token": "abc"})
    assert resp.code == 200
    assert resp.message == "ok"
    assert resp.data == {"token": "abc"}
    assert resp.timestamp > 0


def test_make_error_structure():
    resp = make_error(401, "未授权")
    assert resp.code == 401
    assert resp.message == "未授权"
    assert resp.data is None


def test_app_error_fields():
    err = AppError(code=403, message="无权限")
    assert err.code == 403
    assert err.message == "无权限"


@pytest.mark.asyncio
async def test_get_db_yields_async_session():
    """get_db() 应当 yield 一个 AsyncSession。"""
    gen = get_db()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    try:
        await gen.aclose()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_access_token_round_trip():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, role="student")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == user_id
    assert payload["role"] == "student"
    assert payload["type"] == "access"


def test_refresh_token_round_trip():
    user_id = str(uuid.uuid4())
    token = create_refresh_token(user_id=user_id)
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_wrong_token_type_raises():
    user_id = str(uuid.uuid4())
    access_token = create_access_token(user_id=user_id, role="student")
    with pytest.raises(JWTError):
        decode_token(access_token, expected_type="refresh")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_upsert_user_creates_new_user(db_session):
    openid = f"test_openid_{uuid.uuid4().hex[:8]}"
    user = await upsert_user(db_session, openid=openid)
    assert user.openid == openid
    assert user.role == "student"
    assert user.is_active is True
    assert user.id is not None


@pytest.mark.asyncio
async def test_upsert_user_returns_existing(db_session):
    openid = f"test_openid_{uuid.uuid4().hex[:8]}"
    user1 = await upsert_user(db_session, openid=openid)
    user2 = await upsert_user(db_session, openid=openid)
    assert user1.id == user2.id


@pytest.mark.asyncio
async def test_wx_login_returns_tokens(client: AsyncClient):
    """wx-login: mock 微信 API，验证返回 JWT 双 token。"""
    with patch(
        "app.services.auth_service.wechat_code2session",
        new_callable=AsyncMock,
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"wx_login_test_{uuid.uuid4().hex[:8]}"}
        response = await client.post(
            "/api/v1/auth/wx-login",
            json={"code": "fake_wx_code"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["access_token"] != ""
    assert body["data"]["refresh_token"] != ""
    assert body["data"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_wx_login_bad_wechat_code_returns_401(client: AsyncClient):
    """微信 API 返回错误时，接口返回 401。"""
    with patch(
        "app.services.auth_service.wechat_code2session",
        new_callable=AsyncMock,
    ) as mock_wx:
        from app.core.exceptions import AppError
        mock_wx.side_effect = AppError(code=401, message="微信登录失败")
        response = await client.post(
            "/api/v1/auth/wx-login",
            json={"code": "bad_code"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == 401


@pytest.mark.asyncio
async def test_refresh_token_returns_new_access_token(client: AsyncClient):
    """用有效 refresh_token 换取新 access_token。"""
    with patch(
        "app.services.auth_service.wechat_code2session",
        new_callable=AsyncMock,
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"wx_refresh_test_{uuid.uuid4().hex[:8]}"}
        login_resp = await client.post(
            "/api/v1/auth/wx-login",
            json={"code": "test_code"},
        )

    refresh_token = login_resp.json()["data"]["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    new_access = resp.json()["data"]["access_token"]
    assert new_access != ""


@pytest.mark.asyncio
async def test_users_me_returns_profile(client: AsyncClient):
    """携带有效 access_token 可以访问 /users/me。"""
    with patch(
        "app.services.auth_service.wechat_code2session",
        new_callable=AsyncMock,
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"wx_me_test_{uuid.uuid4().hex[:8]}"}
        login_resp = await client.post("/api/v1/auth/wx-login", json={"code": "t"})

    token = login_resp.json()["data"]["access_token"]

    me_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["code"] == 200
    assert body["data"]["role"] == "student"
    assert body["data"]["is_active"] is True
    assert body["data"]["id"] != ""  # UUID string present


@pytest.mark.asyncio
async def test_users_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_me_with_bad_token_returns_401(client: AsyncClient):
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer totally_invalid_token"},
    )
    assert response.status_code == 401
