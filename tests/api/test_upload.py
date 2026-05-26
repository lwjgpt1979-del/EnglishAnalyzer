import pytest

from app.core.config import settings


def test_cos_config_fields_exist():
    """Settings 包含所有 COS 字段。"""
    assert hasattr(settings, "cos_secret_id")
    assert hasattr(settings, "cos_secret_key")
    assert hasattr(settings, "cos_bucket")
    assert hasattr(settings, "cos_region")
    assert hasattr(settings, "cos_base_url")


def test_cos_dev_mode_default():
    """默认（placeholder）配置处于 dev 模式。"""
    assert settings.cos_secret_key.startswith("placeholder")
