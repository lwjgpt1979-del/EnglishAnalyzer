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


import uuid
from unittest.mock import MagicMock, patch


def test_generate_presign_dev_mode_structure():
    """dev 模式返回正确的结构（无需 COS 凭证）。"""
    from app.services.upload_service import generate_presign

    result = generate_presign(
        user_id=uuid.uuid4(),
        content_type="image/jpeg",
    )
    assert "presign_url" in result
    assert "file_url" in result
    assert "key" in result
    assert "expires_in" in result
    assert isinstance(result["expires_in"], int)
    assert result["expires_in"] > 0


def test_generate_presign_key_format():
    """key 格式为 uploads/{user_id}/{YYYYMMDD}/{8chars}.{ext}。"""
    from app.services.upload_service import generate_presign

    user_id = uuid.uuid4()
    result = generate_presign(user_id=user_id, content_type="image/png")
    key = result["key"]

    parts = key.split("/")
    assert parts[0] == "uploads"
    assert parts[1] == str(user_id)
    assert len(parts[2]) == 8 and parts[2].isdigit()   # YYYYMMDD
    filename = parts[3]
    assert filename.endswith(".png")
    assert len(filename) == 12   # 8 chars + "." + 3 chars


def test_generate_presign_all_content_types():
    """所有允许的 content_type 均能生成正确扩展名。"""
    from app.services.upload_service import ALLOWED_CONTENT_TYPES, generate_presign

    for ct, ext in ALLOWED_CONTENT_TYPES.items():
        result = generate_presign(user_id=uuid.uuid4(), content_type=ct)
        assert result["key"].endswith(f".{ext}"), f"{ct} should produce .{ext}"


def test_generate_presign_dev_mode_mock_urls():
    """dev 模式返回含 'mock' 或 'dev' 的 URL（不调用真实 COS）。"""
    from app.services.upload_service import generate_presign

    result = generate_presign(user_id=uuid.uuid4(), content_type="image/jpeg")
    # dev 模式 URL 包含 mock 或 dev 标识
    assert "mock" in result["presign_url"] or "dev" in result["presign_url"]


def test_generate_presign_prod_mode():
    """prod 模式调用 COS SDK 的 get_presigned_url。"""
    from app.services.upload_service import generate_presign

    mock_client = MagicMock()
    mock_client.get_presigned_url.return_value = "https://real-cos.example.com/signed"

    with (
        patch("app.services.upload_service._is_cos_dev_mode", return_value=False),
        patch("app.services.upload_service._make_cos_client", return_value=mock_client),
    ):
        result = generate_presign(user_id=uuid.uuid4(), content_type="image/webp")

    mock_client.get_presigned_url.assert_called_once()
    assert result["presign_url"] == "https://real-cos.example.com/signed"
    assert result["key"].endswith(".webp")
