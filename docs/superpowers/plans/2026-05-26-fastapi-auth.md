# FastAPI 基础架构 + 用户认证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建可运行的 FastAPI 后端，实现微信小程序登录（wx.login → JWT），提供受保护的 `/api/v1/users/me` 接口，并在每个请求中注入 PostgreSQL RLS 所需的 `app.current_user_id` 会话变量。

**Architecture:** FastAPI 异步架构，pydantic-settings 管理配置，SQLAlchemy 2.x asyncio 提供异步 DB session（与现有 Alembic 同步 engine 共存），python-jose 签发/验证 JWT（access 2h + refresh 30d），httpx.AsyncClient 调用微信 code2session API。统一响应格式 `{code, message, data, timestamp}`，AppError 异常体系贯穿全栈。RLS 注入通过 `get_rls_db` 依赖实现（SET LOCAL app.current_user_id），不单独启用 PostgreSQL POLICY（留给 migration 0003）。

**Tech Stack:** Python 3.12 · FastAPI 0.115+ · SQLAlchemy 2.x asyncio · psycopg3 · pydantic-settings 2.x · python-jose 3.x · httpx 0.27+ · uvicorn 0.30+ · pytest-asyncio

---

## 文件结构

```
backend/
├── pyproject.toml                    # 修改: 新增 uvicorn, python-jose[cryptography], sqlalchemy[asyncio]
├── .env.example                      # 修改: 新增 WECHAT_APPID, WECHAT_APPSECRET, JWT_SECRET_KEY
├── .env                              # 修改: 同上（本地开发实际值）
└── app/
    ├── main.py                       # 新建: FastAPI app factory, lifespan, 异常处理器, 路由挂载
    ├── core/
    │   ├── config.py                 # 新建: pydantic-settings Settings 单例
    │   ├── database.py               # 修改: 新增 async engine + AsyncSessionLocal + get_db + get_rls_db
    │   ├── security.py               # 新建: create_access_token, create_refresh_token, verify_token, get_current_user
    │   └── exceptions.py             # 新建: AppError + register_exception_handlers
    ├── schemas/
    │   ├── __init__.py               # 新建 (空)
    │   ├── base.py                   # 新建: BaseResponse[T], make_ok(), make_error()
    │   └── auth.py                   # 新建: WxLoginRequest, RefreshRequest, TokenResponse, UserProfileOut
    ├── api/
    │   ├── __init__.py               # 新建 (空)
    │   └── v1/
    │       ├── __init__.py           # 新建 (空)
    │       ├── router.py             # 新建: 聚合 auth + users 路由
    │       ├── auth.py               # 新建: POST /auth/wx-login, POST /auth/refresh
    │       └── users.py              # 新建: GET /users/me
    └── services/
        ├── __init__.py               # 新建 (空)
        └── auth_service.py           # 新建: wechat_code2session(), upsert_user()

tests/
├── api/
│   ├── __init__.py                   # 新建 (空)
│   ├── conftest.py                   # 新建: async test client fixture
│   └── test_auth.py                  # 新建: wx-login / refresh / /users/me 测试
└── models/
    └── test_model_structure.py       # 已有，不修改
```

---

### Task 0: 扩展依赖 + 更新环境变量

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`
- Modify: `backend/.env`

- [ ] **Step 1: 写依赖变更测试**

在 `tests/api/test_auth.py`（先创建空文件）头部添加导入检查，稍后补充；这里先在 `tests/api/__init__.py` 创建空文件：

```bash
mkdir -p tests/api
touch tests/api/__init__.py tests/api/conftest.py tests/api/test_auth.py
```

- [ ] **Step 2: 更新 `backend/pyproject.toml`**

```toml
[project]
name = "enggramer-backend"
version = "0.1.0"
description = "engGramer SaaS — FastAPI backend"
requires-python = ">=3.12"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
]

[tool.pytest.ini_options]
testpaths = ["../tests"]
pythonpath = ["."]
asyncio_mode = "auto"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 3: 安装新依赖**

```bash
cd backend && pip install -e ".[dev]"
```

Expected: `Successfully installed uvicorn-... python-jose-... ...`（无 ERROR）

- [ ] **Step 4: 更新 `backend/.env.example`**

```dotenv
# PostgreSQL 连接（迁移用同步连接）
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/enggramer

# 异步连接（FastAPI 应用使用，Alembic 不用）
ASYNC_DATABASE_URL=postgresql+psycopg_async://user:password@localhost:5432/enggramer

# 微信小程序
WECHAT_APPID=your_wechat_appid
WECHAT_APPSECRET=your_wechat_appsecret

# JWT（生产环境必须换成随机长字符串）
JWT_SECRET_KEY=dev-secret-change-in-production

# 调试模式（生产环境设为 false）
DEBUG=false
```

- [ ] **Step 5: 更新 `backend/.env`（本地实际值）**

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer
ASYNC_DATABASE_URL=postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer
WECHAT_APPID=wx_dev_placeholder
WECHAT_APPSECRET=dev_secret_placeholder
JWT_SECRET_KEY=dev-jwt-secret-for-local-testing-only
DEBUG=true
```

- [ ] **Step 6: 验证导入**

```bash
cd backend && python -c "import uvicorn, jose, httpx, sqlalchemy.ext.asyncio; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/.env.example
git commit -m "feat(deps): add uvicorn, python-jose, httpx for FastAPI auth"
```

---

### Task 1: Config（pydantic-settings Settings）

**Files:**
- Create: `backend/app/core/config.py`
- Test: `tests/api/test_auth.py`（Step 1 写测试）

- [ ] **Step 1: 写测试**

在 `tests/api/test_auth.py` 写：

```python
from app.core.config import settings


def test_settings_loads_database_url():
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_loads_async_database_url():
    assert settings.async_database_url.startswith("postgresql+psycopg_async://")


def test_settings_has_jwt_secret():
    assert len(settings.jwt_secret_key) >= 8
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_settings_loads_database_url -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: 创建 `backend/app/core/config.py`**

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

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_settings_loads_database_url ../tests/api/test_auth.py::test_settings_loads_async_database_url ../tests/api/test_auth.py::test_settings_has_jwt_secret -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py tests/api/test_auth.py tests/api/__init__.py tests/api/conftest.py
git commit -m "feat(config): add pydantic-settings Settings singleton"
```

---

### Task 2: 统一响应格式 + AppError 异常处理

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/base.py`
- Create: `backend/app/core/exceptions.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_make_ok_structure -v
```

Expected: `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: 创建 `backend/app/schemas/__init__.py`（空文件）**

```bash
touch backend/app/schemas/__init__.py
```

- [ ] **Step 4: 创建 `backend/app/schemas/base.py`**

```python
import time
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None
    timestamp: int


def make_ok(data: object = None, message: str = "ok") -> BaseResponse:
    return BaseResponse(
        code=200,
        message=message,
        data=data,
        timestamp=int(time.time()),
    )


def make_error(code: int, message: str) -> BaseResponse:
    return BaseResponse(
        code=code,
        message=message,
        data=None,
        timestamp=int(time.time()),
    )
```

- [ ] **Step 5: 创建 `backend/app/core/exceptions.py`**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.base import make_error


class AppError(Exception):
    """业务异常，统一返回 {code, message} 格式。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.code if exc.code in range(400, 600) else 400,
            content=make_error(exc.code, exc.message).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=make_error(500, "服务器内部错误").model_dump(),
        )
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_make_ok_structure ../tests/api/test_auth.py::test_make_error_structure ../tests/api/test_auth.py::test_app_error_fields -v
```

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/schemas/base.py backend/app/core/exceptions.py tests/api/test_auth.py
git commit -m "feat(schemas): add unified BaseResponse + AppError exception handling"
```

---

### Task 3: Async DB Session（get_db + get_rls_db）

**Files:**
- Modify: `backend/app/core/database.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db


@pytest.mark.asyncio
async def test_get_db_yields_async_session():
    """get_db() 应当 yield 一个 AsyncSession。"""
    gen = get_db()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    # 关闭 session
    try:
        await gen.aclose()
    except StopAsyncIteration:
        pass
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_get_db_yields_async_session -v
```

Expected: `ImportError` 或 `AttributeError`（get_db 尚未实现）

- [ ] **Step 3: 修改 `backend/app/core/database.py`**

```python
import os
from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

# ── Sync engine（Alembic 迁移专用）────────────────────────────────────────────


def get_engine_url() -> str | None:
    """从环境变量读取同步数据库 URL（不存在则返回 None）。"""
    return os.getenv("DATABASE_URL")


def create_sync_engine(url: str | None = None) -> Engine:
    """创建同步 SQLAlchemy engine（供 Alembic 迁移使用）。"""
    db_url = url or get_engine_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_engine(db_url, echo=False)


def create_session_factory(engine: Engine) -> "sessionmaker[Session]":
    """返回 SessionLocal 工厂。"""
    return sessionmaker(engine, autocommit=False, autoflush=False)


# ── Async engine（FastAPI 请求处理专用）────────────────────────────────────────


def _build_async_engine():
    url = os.getenv("ASYNC_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "ASYNC_DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_async_engine(url, echo=os.getenv("DEBUG", "false").lower() == "true")


_async_engine = _build_async_engine()
_async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：yield 一个 AsyncSession，请求结束自动关闭。"""
    async with _async_session_factory() as session:
        yield session


async def get_rls_db(
    session: AsyncSession,
    user_id: str,
) -> AsyncGenerator[AsyncSession, None]:
    """在当前事务中注入 RLS 会话变量 app.current_user_id。

    用法（在 endpoint 依赖中）：
        db = Depends(get_db)
        current_user = Depends(get_current_user)
        await inject_rls(db, str(current_user.id))
        # 之后的 db 操作自动受 RLS 过滤
    """
    await session.execute(
        sa.text("SET LOCAL app.current_user_id = :uid"),
        {"uid": user_id},
    )


async def close_async_engine() -> None:
    """应用关闭时释放连接池（在 lifespan shutdown 中调用）。"""
    await _async_engine.dispose()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_get_db_yields_async_session -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/database.py tests/api/test_auth.py
git commit -m "feat(db): add async engine + get_db + get_rls_db for FastAPI"
```

---

### Task 4: FastAPI App Factory + Health Check

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/router.py`（占位）
- Create: `backend/app/services/__init__.py`
- Create: `tests/api/conftest.py`

- [ ] **Step 1: 写测试**

在 `tests/api/conftest.py` 写：

```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
```

追加到 `tests/api/test_auth.py`：

```python
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_health_check -v
```

Expected: `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: 创建空的 `__init__.py` 文件**

```bash
touch backend/app/api/__init__.py backend/app/api/v1/__init__.py backend/app/services/__init__.py
```

- [ ] **Step 4: 创建 `backend/app/api/v1/router.py`（占位，后续各 Task 追加路由）**

```python
from fastapi import APIRouter

v1_router = APIRouter()

# 各子模块路由将在后续 Task 中 include 进来
```

- [ ] **Step 5: 创建 `backend/app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import close_async_engine
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup：异步引擎已在模块导入时初始化，此处预留扩展点
    yield
    # shutdown：释放连接池
    await close_async_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="engGramer API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS（开发阶段开放，生产按域名收窄）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 统一异常处理
    register_exception_handlers(app)

    # 路由挂载
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_health_check -v
```

Expected: `1 passed`

- [ ] **Step 7: 手动启动服务器验证**

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

另开终端：
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/app/api/__init__.py backend/app/api/v1/__init__.py backend/app/api/v1/router.py backend/app/services/__init__.py tests/api/conftest.py tests/api/test_auth.py
git commit -m "feat(app): FastAPI app factory + health check endpoint"
```

---

### Task 5: JWT Security（签发 + 验证 + get_current_user 依赖）

**Files:**
- Create: `backend/app/core/security.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
import uuid
from jose import JWTError
import pytest
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_access_token_round_trip -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.security'`

- [ ] **Step 3: 创建 `backend/app/core/security.py`**

```python
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.d1_users import User

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, role: str) -> str:
    """签发 access token，有效期 2 小时（见 Tech Spec §1.5）。"""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """签发 refresh token，有效期 30 天（见 Tech Spec §1.5）。"""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict:
    """解码并验证 JWT。type 不匹配时抛出 JWTError。"""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise JWTError(f"token type mismatch: expected {expected_type}")
    return payload


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """FastAPI 依赖：从 Authorization Bearer token 中解析当前用户。

    未携带 token 或 token 无效时返回 401。
    用户被封禁（is_active=False）时返回 403。
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未授权，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except JWTError:
        raise unauthorized

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise unauthorized

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被封禁")

    return user
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_access_token_round_trip ../tests/api/test_auth.py::test_refresh_token_round_trip ../tests/api/test_auth.py::test_wrong_token_type_raises -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py tests/api/test_auth.py
git commit -m "feat(security): JWT create/verify + get_current_user dependency"
```

---

### Task 6: Auth Service（微信登录 + 用户 Upsert）

**Files:**
- Create: `backend/app/services/auth_service.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.auth_service import upsert_user
from app.core.database import _async_session_factory


@pytest.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


async def test_upsert_user_creates_new_user(db_session):
    openid = f"test_openid_{uuid.uuid4().hex[:8]}"
    user = await upsert_user(db_session, openid=openid)
    assert user.openid == openid
    assert user.role == "student"
    assert user.is_active is True
    assert user.id is not None


async def test_upsert_user_returns_existing(db_session):
    openid = f"test_openid_{uuid.uuid4().hex[:8]}"
    user1 = await upsert_user(db_session, openid=openid)
    user2 = await upsert_user(db_session, openid=openid)
    assert user1.id == user2.id
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_upsert_user_creates_new_user -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.auth_service'`

- [ ] **Step 3: 创建 `backend/app/services/auth_service.py`**

```python
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User


async def wechat_code2session(code: str) -> dict:
    """调用微信 jscode2session 接口，返回 {openid, session_key}。

    文档：https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.wechat_code2session_url,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()

    if data.get("errcode") and data["errcode"] != 0:
        raise AppError(
            code=401,
            message=f"微信登录失败（{data.get('errmsg', 'unknown')}），请重试",
        )

    openid = data.get("openid")
    if not openid:
        raise AppError(code=401, message="微信未返回 openid，请重试")

    return {"openid": openid, "session_key": data.get("session_key", "")}


async def upsert_user(db: AsyncSession, *, openid: str) -> User:
    """按 openid 查找用户；不存在则创建（默认 role=student）。

    注意：session_key 不落库，仅在 Auth 层短暂使用（Tech Spec §1.2）。
    """
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            openid=openid,
            role="student",
            is_active=True,
        )
        db.add(user)
        await db.flush()   # 获取 id，但不 commit（让调用方控制事务边界）

    return user
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_upsert_user_creates_new_user ../tests/api/test_auth.py::test_upsert_user_returns_existing -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py tests/api/test_auth.py
git commit -m "feat(service): auth service — wechat_code2session + upsert_user"
```

---

### Task 7: Auth Schemas + 认证接口（wx-login / refresh）

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
async def test_wx_login_returns_tokens(client: AsyncClient):
    """wx-login 接口：mock 微信 API，验证返回 JWT 双 token。"""
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


async def test_wx_login_bad_wechat_code_returns_401(client: AsyncClient):
    """微信 API 返回 errcode 时，接口返回 401。"""
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


async def test_refresh_token_returns_new_access_token(client: AsyncClient):
    """用有效 refresh_token 换取新 access_token。"""
    # 先登录
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

    # 用 refresh_token 换 access_token
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    new_access = resp.json()["data"]["access_token"]
    assert new_access != ""
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_wx_login_returns_tokens -v
```

Expected: `404 Not Found`（路由不存在）

- [ ] **Step 3: 创建 `backend/app/schemas/auth.py`**

```python
from pydantic import BaseModel


class WxLoginRequest(BaseModel):
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfileOut(BaseModel):
    id: str
    role: str
    nickname: str | None
    avatar_url: str | None
    is_active: bool
```

- [ ] **Step 4: 创建 `backend/app/api/v1/auth.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.auth import RefreshRequest, TokenResponse, WxLoginRequest
from app.schemas.base import BaseResponse, make_ok
from app.services.auth_service import upsert_user, wechat_code2session
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wx-login", response_model=BaseResponse[TokenResponse])
async def wx_login(
    body: WxLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """微信小程序登录。

    前端调用 wx.login() 获取 code，发送到此接口。
    后端用 code 换取 openid，upsert 用户，返回 JWT 双 token。
    session_key 不落库，不透传前端（Tech Spec §1.2）。
    """
    wx_data = await wechat_code2session(body.code)
    user = await upsert_user(db, openid=wx_data["openid"])
    await db.commit()

    return make_ok(
        TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id)),
        )
    )


@router.post("/refresh", response_model=BaseResponse[TokenResponse])
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用 refresh_token 换取新 access_token。

    refresh_token 过期或类型错误时返回 401。
    """
    from sqlalchemy import select
    import uuid
    from app.models.d1_users import User

    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except JWTError:
        raise AppError(code=401, message="refresh_token 无效或已过期，请重新登录")

    user_id = payload.get("sub", "")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppError(code=401, message="用户不存在或已被封禁")

    return make_ok(
        TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id)),
        )
    )
```

- [ ] **Step 5: 修改 `backend/app/api/v1/router.py`，挂载 auth 路由**

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_wx_login_returns_tokens ../tests/api/test_auth.py::test_wx_login_bad_wechat_code_returns_401 ../tests/api/test_auth.py::test_refresh_token_returns_new_access_token -v
```

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/v1/auth.py backend/app/api/v1/router.py tests/api/test_auth.py
git commit -m "feat(auth): wx-login + refresh endpoints with JWT double token"
```

---

### Task 8: GET /users/me（受保护接口 + RLS 注入）

**Files:**
- Create: `backend/app/api/v1/users.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: 写测试**

追加到 `tests/api/test_auth.py`：

```python
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


async def test_users_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_users_me_with_bad_token_returns_401(client: AsyncClient):
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer totally_invalid_token"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py::test_users_me_returns_profile -v
```

Expected: `404 Not Found`

- [ ] **Step 3: 创建 `backend/app/api/v1/users.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.auth import UserProfileOut
from app.schemas.base import BaseResponse, make_ok

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=BaseResponse[UserProfileOut])
async def get_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """返回当前登录用户的基本信息，同时注入 RLS 会话变量。

    RLS 注入：SET LOCAL app.current_user_id = <user_id>
    后续在同一 session 内的查询自动受 PostgreSQL RLS 过滤（Tech Spec §2）。
    """
    await get_rls_db(db, str(current_user.id))

    return make_ok(
        UserProfileOut(
            id=str(current_user.id),
            role=current_user.role,
            nickname=current_user.nickname,
            avatar_url=current_user.avatar_url,
            is_active=current_user.is_active,
        )
    )
```

- [ ] **Step 4: 修改 `backend/app/api/v1/router.py`，挂载 users 路由**

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
```

- [ ] **Step 5: 运行全部测试**

```bash
cd backend && python -m pytest ../tests/api/test_auth.py -v
```

Expected: 所有测试通过（约 14-16 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/users.py backend/app/api/v1/router.py tests/api/test_auth.py
git commit -m "feat(users): GET /users/me with JWT auth + RLS session variable injection"
```

---

### Task 9: 集成验证 + 全量测试

**Files:** 无新文件，仅验证

- [ ] **Step 1: 运行所有测试（含已有的模型结构测试）**

```bash
cd backend && python -m pytest ../tests/ -v
```

Expected: 所有测试通过（model 35 + api ~14 = 约 49 个测试）

- [ ] **Step 2: 手动启动服务器做 E2E 验证**

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 3: 验证 health check**

```bash
curl -s http://localhost:8000/health | python -m json.tool
```

Expected:
```json
{"status": "ok"}
```

- [ ] **Step 4: 验证 OpenAPI 文档可访问（DEBUG=true 模式）**

浏览器打开 `http://localhost:8000/docs`，应看到 FastAPI Swagger UI，含以下接口：
- `POST /api/v1/auth/wx-login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/users/me`
- `GET /health`

- [ ] **Step 5: 验证无 token 访问 /users/me 被拒绝**

```bash
curl -s http://localhost:8000/api/v1/users/me | python -m json.tool
```

Expected:
```json
{
  "detail": "未授权，请重新登录"
}
```

- [ ] **Step 6: 最终 Commit**

```bash
git add .
git commit -m "feat(fastapi-auth): FastAPI 基础架构 + 用户认证完成

- Settings (pydantic-settings), AppError, BaseResponse
- Async SQLAlchemy engine + get_db + get_rls_db
- JWT (access 2h + refresh 30d) with python-jose
- POST /api/v1/auth/wx-login (WeChat code2session → upsert user → JWT)
- POST /api/v1/auth/refresh (refresh token → new access token)
- GET /api/v1/users/me (Bearer token required + RLS injection)
- 约 14 个 API 测试全部通过"
```

---

## 自检

### 1. Spec 覆盖

| Tech Spec 要求 | 对应 Task |
|---|---|
| 统一响应格式 `{code, message, data, timestamp}` | Task 2 |
| JWT access 2h + refresh 30d（§1.5）| Task 5 |
| 微信 openid 不作业务主键（§1.2）| Task 6（openid 仅用于查找，返回 user_id）|
| Authorization: Bearer token（§1.2）| Task 5, 8 |
| API 路径 `/api/v1/...`（§1.2）| Task 4, 7, 8 |
| RLS SET LOCAL app.current_user_id（§2）| Task 3, 8 |
| session_key 不透传业务层（§1.2）| Task 6（仅在 auth_service 中使用，不存储）|

### 2. 占位符扫描

无 TBD / TODO / 实现后补充等占位符。

### 3. 类型一致性

- `wechat_code2session()` 返回 `dict`，在 `wx_login` 端点中取 `["openid"]` ✅
- `upsert_user()` 参数 `openid: str`，在 `wx_login` 中传 `wx_data["openid"]` ✅
- `create_access_token(user_id: str, role: str)`，`decode_token` 返回 `dict` ✅
- `get_current_user` 返回 `User`，`/users/me` 接收 `User` ✅
- `get_rls_db(session, user_id: str)`，调用时传 `str(current_user.id)` ✅
