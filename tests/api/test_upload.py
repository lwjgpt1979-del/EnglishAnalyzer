import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

# ── Config 单元测试 ───────────────────────────────────────────────────────────


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


# ── Upload Service 单元测试 ───────────────────────────────────────────────────


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
    from app.services.upload_service import ALLOWED_CONTENT_TYPES, generate_presign

    user_id = uuid.uuid4()
    result = generate_presign(user_id=user_id, content_type="image/png")
    key = result["key"]

    parts = key.split("/")
    assert parts[0] == "uploads"
    assert parts[1] == str(user_id)
    assert len(parts[2]) == 8 and parts[2].isdigit()  # YYYYMMDD
    filename = parts[3]
    ext = ALLOWED_CONTENT_TYPES["image/png"]
    assert filename.endswith(f".{ext}")
    assert len(filename) == 8 + 1 + len(ext)  # 8-char hex + "." + extension


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


# ── API 集成测试 ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"upload_test_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, f"wx-login failed: {resp.text}"
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_presign_requires_auth(client: AsyncClient):
    """未登录返回 401。"""
    resp = await client.post(
        "/api/v1/upload/presign",
        json={"content_type": "image/jpeg"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_presign_invalid_content_type(
    client: AsyncClient, auth_headers
):
    """不允许的 content_type 返回 400。"""
    resp = await client.post(
        "/api/v1/upload/presign",
        json={"content_type": "application/pdf"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 400


@pytest.mark.asyncio
async def test_upload_presign_success(client: AsyncClient, auth_headers):
    """合法请求返回 200，响应含 presign_url / file_url / key / expires_in。"""
    resp = await client.post(
        "/api/v1/upload/presign",
        json={"content_type": "image/png"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert "presign_url" in data
    assert "file_url" in data
    assert "key" in data
    assert "expires_in" in data
    assert data["expires_in"] == 600
    assert data["key"].endswith(".png")


@pytest.mark.asyncio
async def test_upload_presign_key_contains_user_path(
    client: AsyncClient, auth_headers
):
    """返回的 key 路径以 'uploads/' 开头，file_url 包含该 key。"""
    resp = await client.post(
        "/api/v1/upload/presign",
        json={"content_type": "image/jpeg"},
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["key"].startswith("uploads/")
    assert data["key"] in data["file_url"] or data["key"] in data["presign_url"]
