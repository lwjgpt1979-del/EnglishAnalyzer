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
