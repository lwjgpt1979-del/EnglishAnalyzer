# 图片上传 + COS 预签名 URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `POST /api/v1/upload/presign`，为客户端生成腾讯云 COS 预签名 PUT URL，让微信小程序直接上传图片到 COS，无需经过后端中转，上传后 `file_url` 直接填入 `WrongQuestion.source_image_url`。

**Architecture:** 预签名 URL 模式——后端校验 content_type、生成对象 Key、调用 COS SDK 签名，返回 `{presign_url, file_url, key, expires_in}`；客户端直接 PUT 到 `presign_url`，成功后用 `file_url` 创建错题。Dev 模式（`cos_secret_key` 以 "placeholder" 开头）跳过 COS 调用，返回 mock URL，保证本地开发无需真实 COS 凭证。

**Tech Stack:** FastAPI 0.115 · cos-python-sdk-v5（腾讯云 COS 官方 SDK）· pydantic v2 · pytest-asyncio STRICT

---

## File Structure

```
New files:
  backend/app/services/upload_service.py     # 预签名 URL 生成逻辑（dev/prod 双模式）
  backend/app/api/v1/upload.py               # POST /upload/presign endpoint
  tests/api/test_upload.py                   # 全部上传测试

Modified files:
  backend/pyproject.toml                     # 添加 cos-python-sdk-v5 依赖
  backend/app/core/config.py                 # 添加 COS 配置字段
  backend/app/api/v1/router.py               # 注册 upload_router
  backend/.env                               # 添加 COS 占位环境变量（不提交）
```

**Endpoint:**
```
POST /api/v1/upload/presign   Bearer JWT 必须；body: {"content_type": "image/jpeg"}
                               返回 BaseResponse[PresignOut]
```

**Allowed content types:**
- `image/jpeg` → ext `jpg`
- `image/png`  → ext `png`
- `image/webp` → ext `webp`
- `image/gif`  → ext `gif`

**Object key format:** `uploads/{user_id}/{YYYYMMDD}/{8位uuid}.{ext}`
例：`uploads/abc...123/20260526/deadbeef.jpg`

**COS file URL format:** `{cos_base_url}/{key}`
例：`https://enggramer-1250000000.cos.ap-guangzhou.myqcloud.com/uploads/.../deadbeef.jpg`

**Key model facts（开始前确认）：**
- `Settings` 位于 `backend/app/core/config.py`，用 `pydantic_settings.BaseSettings`
- `BaseResponse` / `make_ok` / `AppError` 在 `app.schemas.base` / `app.core.exceptions`
- 所有 protected endpoint 必须先调 `await get_rls_db(db, str(current_user.id))`
- 但 `/upload/presign` **不需要 DB 访问**，所以无需 `get_rls_db`；只需 `get_current_user`
- pytest 异步测试使用 `@pytest.mark.asyncio` + `@pytest_asyncio.fixture`

---

## Task 0: Config + Dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env` （不提交）
- Create: `tests/api/test_upload.py`

- [ ] **Step 1: 创建 `tests/api/test_upload.py` 并写失败测试（config 部分）**

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -v 2>&1 | head -20
```

Expected: `FAILED` with `AttributeError: Settings object has no attribute 'cos_secret_id'`

- [ ] **Step 3: 添加 COS 依赖到 `backend/pyproject.toml`**

在 `dependencies` 列表末尾加一行：

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "alembic>=1.14.0",
    "psycopg[binary]>=3.1.0",
    "pydantic-settings>=2.3.0",
    "python-dotenv>=1.0.1",
    "python-jose[cryptography]>=3.3.0",
    "httpx>=0.27.0",
    "anthropic>=0.40.0",
    "cos-python-sdk-v5>=1.9.30",
]
```

- [ ] **Step 4: 安装新依赖**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
pip install cos-python-sdk-v5 2>&1 | tail -5
```

Expected: `Successfully installed cos-python-sdk-v5-...`

- [ ] **Step 5: 添加 COS 字段到 `backend/app/core/config.py`**

在 `# 应用` 注释之前插入：

```python
    # 腾讯云 COS 图片存储
    cos_secret_id: str = "placeholder_secret_id"
    cos_secret_key: str = "placeholder_secret_key"
    cos_bucket: str = "enggramer-dev-1234567890"
    cos_region: str = "ap-guangzhou"
    cos_base_url: str = "https://enggramer-dev-1234567890.cos.ap-guangzhou.myqcloud.com"
```

完整 `config.py` 结果：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库
    database_url: str
    async_database_url: str

    # 微信小程序
    wechat_appid: str = "wx_dev_placeholder"
    wechat_appsecret: str = "dev_secret_placeholder"
    wechat_code2session_url: str = (
        "https://api.weixin.qq.com/sns/jscode2session"
    )

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120   # 2 小时
    refresh_token_expire_days: int = 30

    # AI 分析（Anthropic Claude）
    anthropic_api_key: str = "sk-ant-placeholder-for-dev"

    # 微信支付 v3
    wechat_pay_mch_id: str = "placeholder_mch_id"
    wechat_pay_api_key_v3: str = "placeholder32charsapikey12345678"  # 32 chars
    wechat_pay_cert_serial: str = "placeholder_cert_serial"
    wechat_pay_private_key_pem: str = "placeholder_private_key_pem"
    wechat_pay_notify_url: str = "https://api.example.com/api/v1/webhooks/wx-pay"
    wechat_pay_skip_sig_verify: bool = True

    # 腾讯云 COS 图片存储
    cos_secret_id: str = "placeholder_secret_id"
    cos_secret_key: str = "placeholder_secret_key"
    cos_bucket: str = "enggramer-dev-1234567890"
    cos_region: str = "ap-guangzhou"
    cos_base_url: str = "https://enggramer-dev-1234567890.cos.ap-guangzhou.myqcloud.com"

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
```

- [ ] **Step 6: 追加 COS 占位配置到 `backend/.env`**（注意：.env 不提交）

```bash
cat >> /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend/.env << 'EOF'

# 腾讯云 COS（生产环境替换为真实值）
COS_SECRET_ID=placeholder_secret_id
COS_SECRET_KEY=placeholder_secret_key
COS_BUCKET=enggramer-dev-1234567890
COS_REGION=ap-guangzhou
COS_BASE_URL=https://enggramer-dev-1234567890.cos.ap-guangzhou.myqcloud.com
EOF
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -v
```

Expected: `2 passed`

- [ ] **Step 8: 运行全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `119 passed`（117 + 2 新增）

- [ ] **Step 9: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/pyproject.toml backend/app/core/config.py tests/api/test_upload.py
git commit -m "feat(config): add COS config fields + cos-python-sdk-v5 dependency"
```

---

## Task 1: Upload Schemas + Service

**Files:**
- Create: `backend/app/services/upload_service.py`
- Modify: `tests/api/test_upload.py` (append)

- [ ] **Step 1: 追加失败测试**

READ `tests/api/test_upload.py` 末尾，追加：

```python
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
    """dev 模式返回含 'mock' 的 URL（不调用真实 COS）。"""
    from app.services.upload_service import generate_presign

    result = generate_presign(user_id=uuid.uuid4(), content_type="image/jpeg")
    # dev 模式 URL 包含 mock 标识
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -k "generate_presign" -v 2>&1 | head -20
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.services.upload_service'`

- [ ] **Step 3: 创建 `backend/app/services/upload_service.py`**

```python
"""图片上传预签名 URL 服务。

流程：后端生成 COS 预签名 PUT URL → 客户端直接 PUT 到 COS → 用 file_url 创建 WrongQuestion。
Dev 模式（cos_secret_key 以 'placeholder' 开头）跳过 COS，返回 mock URL。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import settings

# ── 常量 ─────────────────────────────────────────────────────────────────────

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

PRESIGN_EXPIRES: int = 600  # 10 分钟（秒）


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _is_cos_dev_mode() -> bool:
    """True 当 cos_secret_key 为占位符——无法调用真实 COS。"""
    return settings.cos_secret_key.startswith("placeholder")


def _make_cos_client():  # type: ignore[return]
    """创建 COS S3 客户端（仅 prod 模式调用）。"""
    from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]

    config = CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key,
    )
    return CosS3Client(config)


def _build_key(user_id: uuid.UUID, ext: str) -> str:
    """生成唯一对象 Key：uploads/{user_id}/{YYYYMMDD}/{8位uuid}.{ext}"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:8]
    return f"uploads/{user_id}/{today}/{short_id}.{ext}"


# ── 公开接口 ──────────────────────────────────────────────────────────────────


def generate_presign(
    *,
    user_id: uuid.UUID,
    content_type: str,
) -> dict[str, str | int]:
    """生成 COS 预签名 PUT URL。

    参数：
        user_id: 当前登录用户 ID（用于 key 路径隔离）
        content_type: 已通过白名单校验的 MIME 类型（如 'image/jpeg'）

    返回：
        {presign_url, file_url, key, expires_in}
    """
    ext = ALLOWED_CONTENT_TYPES[content_type]
    key = _build_key(user_id, ext)

    if _is_cos_dev_mode():
        mock_base = "https://mock-cos.dev"
        return {
            "presign_url": f"{mock_base}/{key}?X-Mock-Sig=dev",
            "file_url": f"{mock_base}/{key}",
            "key": key,
            "expires_in": PRESIGN_EXPIRES,
        }

    client = _make_cos_client()
    presign_url: str = client.get_presigned_url(
        Method="PUT",
        Bucket=settings.cos_bucket,
        Key=key,
        Expired=PRESIGN_EXPIRES,
    )
    file_url = f"{settings.cos_base_url}/{key}"
    return {
        "presign_url": presign_url,
        "file_url": file_url,
        "key": key,
        "expires_in": PRESIGN_EXPIRES,
    }
```

- [ ] **Step 4: 运行目标测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -k "generate_presign" -v
```

Expected: `5 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `124 passed`（119 + 5 新增）

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/upload_service.py tests/api/test_upload.py
git commit -m "feat(service): COS presign URL generation — dev/prod dual mode"
```

---

## Task 2: Upload API Endpoint + Router

**Files:**
- Create: `backend/app/api/v1/upload.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_upload.py` (append)

- [ ] **Step 1: 追加 API 测试**

READ `tests/api/test_upload.py` 末尾，追加：

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app


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
    """返回的 key 路径以 'uploads/' 开头，文件_url 包含该 key。"""
    resp = await client.post(
        "/api/v1/upload/presign",
        json={"content_type": "image/jpeg"},
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["key"].startswith("uploads/")
    assert data["key"] in data["file_url"] or data["key"] in data["presign_url"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -k "presign_requires or presign_invalid or presign_success or presign_key" -v 2>&1 | head -20
```

Expected: `FAILED`（路由未注册 → 404 或 ImportError）

- [ ] **Step 3: 创建 `backend/app/api/v1/upload.py`**

```python
"""图片上传预签名 URL API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services.upload_service import ALLOWED_CONTENT_TYPES, PRESIGN_EXPIRES, generate_presign

router = APIRouter(prefix="/upload", tags=["upload"])

UserDep = Annotated[User, Depends(get_current_user)]

# ── Schemas ───────────────────────────────────────────────────────────────────


class PresignRequest(BaseModel):
    """预签名 URL 请求体。"""

    content_type: str = Field(
        ...,
        description="图片 MIME 类型，允许：image/jpeg · image/png · image/webp · image/gif",
    )


class PresignOut(BaseModel):
    """预签名 URL 响应。"""

    presign_url: str = Field(..., description="PUT 上传 URL，有效期10分钟")
    file_url: str = Field(..., description="上传成功后的最终访问 URL")
    key: str = Field(..., description="COS 对象 Key")
    expires_in: int = Field(..., description=f"预签名 URL 有效期（秒），固定 {PRESIGN_EXPIRES}")


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/presign", response_model=BaseResponse[PresignOut])
async def get_upload_presign(body: PresignRequest, current_user: UserDep):
    """为当前用户生成图片上传预签名 PUT URL。

    1. 校验 content_type 在白名单内（jpeg / png / webp / gif）。
    2. 生成带用户 ID 隔离的 COS 对象 Key。
    3. 返回预签名 URL（dev 模式返回 mock URL）。

    客户端拿到 presign_url 后直接 HTTP PUT（body 为图片二进制，无 Content-Type 限制），
    成功后用 file_url 调用 POST /wrong-questions/ 创建错题。
    """
    if body.content_type not in ALLOWED_CONTENT_TYPES:
        allowed = "、".join(ALLOWED_CONTENT_TYPES)
        raise AppError(code=400, message=f"不支持的图片类型：{body.content_type}，允许：{allowed}")

    result = generate_presign(
        user_id=current_user.id,
        content_type=body.content_type,
    )
    return make_ok(PresignOut(**result))
```

- [ ] **Step 4: 更新 `backend/app/api/v1/router.py`**

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.diagnosis import router as diagnosis_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.orders import router as orders_router
from app.api.v1.upload import router as upload_router
from app.api.v1.users import router as users_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.wrong_questions import router as wrong_questions_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(wrong_questions_router)
v1_router.include_router(memberships_router)
v1_router.include_router(orders_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(diagnosis_router)
v1_router.include_router(upload_router)
```

- [ ] **Step 5: 运行 API 测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_upload.py -k "presign_requires or presign_invalid or presign_success or presign_key" -v
```

Expected: `4 passed`

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `128 passed`（124 + 4 新增）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/upload.py backend/app/api/v1/router.py tests/api/test_upload.py
git commit -m "feat(api): POST /upload/presign — COS presigned URL endpoint"
```

---

## Task 3: 集成验证 + Push + 归档 D-064

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 全部 PASS（≥128 个）

- [ ] **Step 2: 启动 live 服务器，验证新端点**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
uvicorn app.main:app --port 8022 --log-level warning &
sleep 3

# 健康检查
curl -s http://localhost:8022/health | python3 -m json.tool

# /docs 正常
curl -s -o /dev/null -w "%{http_code}" http://localhost:8022/docs
echo " /docs"

# /upload/presign 无 token → 401
curl -s -X POST http://localhost:8022/api/v1/upload/presign \
  -H "Content-Type: application/json" \
  -d '{"content_type":"image/jpeg"}' | python3 -m json.tool

pkill -f "uvicorn app.main:app" 2>/dev/null || true
```

Expected:
- `/health` → `{"status": "ok"}`
- `/docs` → `200`
- `/upload/presign` 无 token → 401（`"未授权，请重新登录"`）

- [ ] **Step 3: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 4: 追加 D-064 到 `docs/决策归档.md`**

在文件顶部 `## D-063` 段落之前插入（倒序追加）：

```markdown
## D-064｜图片上传预签名 URL：Tasks 0-3 全量交付

**日期：** 2026-05-26
**背景：** 错题提交目前要求前端手填图片 URL；实现真实图片上传闭环，让微信小程序直接把相册/拍照图片上传到腾讯云 COS，上传后 file_url 填入 WrongQuestion.source_image_url。
**结论：**
1. **依赖与配置（Task 0）：** 引入 `cos-python-sdk-v5`；Settings 新增 5 个 COS 字段（cos_secret_id / cos_secret_key / cos_bucket / cos_region / cos_base_url），默认全为 placeholder，dev 模式下无需真实 COS 凭证。
2. **预签名服务（Task 1）：** `generate_presign(*, user_id, content_type)` 生成 COS 预签名 PUT URL；Key 格式 `uploads/{user_id}/{YYYYMMDD}/{8位uuid}.{ext}`，保证用户隔离和去重；Dev 模式（cos_secret_key 以 "placeholder" 开头）跳过 SDK，返回 mock URL；常量 `ALLOWED_CONTENT_TYPES`（jpeg/png/webp/gif → 扩展名）和 `PRESIGN_EXPIRES=600`（10分钟）。
3. **API（Task 2）：** `POST /api/v1/upload/presign`，Bearer JWT 必须（无 DB 访问，故无需 get_rls_db）；content_type 白名单校验 → AppError(400)；返回 `BaseResponse[PresignOut]`（presign_url / file_url / key / expires_in）。Schemas（PresignRequest / PresignOut）与 endpoint 同文件，因无需跨文件复用。
4. **上传流程决策：** 采用预签名 PUT 模式（非后端代理）——后端不接触图片 binary，无带宽/存储开销；客户端直接 PUT 到 COS，成功后用 file_url 调用 POST /wrong-questions/ 创建错题；预签名有效期 10 分钟，足够用户选图+上传。
5. **不做内容审核：** MVP 阶段跳过图片内容审核（COS 数据万象 CI）；产品层已限制为教学错题场景，风险可接受；上线后视运营情况决定是否接入。
**影响范围：** 全量测试 ≥128 个；1 个新端点；已推送 GitHub main 分支。

---

```

- [ ] **Step 5: 提交归档并推送**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-064 — image upload with COS presigned URL complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | Task |
|------|------|
| 依赖 cos-python-sdk-v5 | Task 0 pyproject.toml |
| COS 环境变量（5个）| Task 0 config.py |
| Dev 模式跳过 COS | Task 1 `_is_cos_dev_mode()` |
| generate_presign() 接口 | Task 1 upload_service.py |
| Key 路径含 user_id 隔离 | Task 1 `_build_key()` |
| content_type 白名单校验 | Task 2 endpoint AppError(400) |
| POST /upload/presign Bearer JWT | Task 2 endpoint + UserDep |
| 无 DB 操作（无需 get_rls_db） | Task 2 endpoint（无 DbDep） |
| 返回 presign_url + file_url + key + expires_in | Task 2 PresignOut |
| 401 未登录 | Task 2 API 测试 |
| 400 非法 content_type | Task 2 API 测试 |
| 200 正常响应含所有字段 | Task 2 API 测试 |

### 2. Placeholder 扫描

- 所有步骤含完整代码 ✅
- 无 TBD/TODO ✅
- 命令含预期输出 ✅
- 测试有具体断言 ✅

### 3. 类型一致性

- `generate_presign(*, user_id: uuid.UUID, content_type: str) -> dict[str, str | int]` — Task 1 定义，Task 2 调用：`generate_presign(user_id=current_user.id, content_type=body.content_type)` ✅
- `PresignOut` 字段（presign_url / file_url / key / expires_in）与 `generate_presign` 返回 dict 键一致 ✅
- `ALLOWED_CONTENT_TYPES` 在 Task 1 service 定义，Task 2 endpoint 直接 import 使用 ✅
- `PRESIGN_EXPIRES` 在 Task 1 定义，Task 2 PresignOut description 和测试 `assert data["expires_in"] == 600` 均使用 600 ✅
