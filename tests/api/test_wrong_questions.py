from app.core.config import settings


def test_settings_has_anthropic_api_key():
    """settings 必须有 anthropic_api_key 字段（值可为 placeholder）。"""
    assert hasattr(settings, "anthropic_api_key")
    assert isinstance(settings.anthropic_api_key, str)
