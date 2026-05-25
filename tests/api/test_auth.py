from app.core.config import settings


def test_settings_loads_database_url():
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_loads_async_database_url():
    assert settings.async_database_url.startswith("postgresql+psycopg_async://")


def test_settings_has_jwt_secret():
    assert len(settings.jwt_secret_key) >= 8
