from httpx import AsyncClient

from app.core.config import settings


def test_settings_loads_database_url():
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_loads_async_database_url():
    assert settings.async_database_url.startswith("postgresql+psycopg_async://")


def test_settings_has_jwt_secret():
    assert len(settings.jwt_secret_key) >= 8


import time
from app.schemas.base import BaseResponse, make_ok, make_error
from app.core.exceptions import AppError


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


import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db


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


import uuid
from jose import JWTError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


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
