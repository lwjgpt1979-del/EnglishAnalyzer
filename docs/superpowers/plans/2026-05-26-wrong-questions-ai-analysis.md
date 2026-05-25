# 错题提交 + AI 分析 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现学生提交英语错题、触发 Claude AI 诊断分析、查询诊断报告的完整 MVP 闭环。

**Architecture:** 学生通过 Bearer JWT 提交错题文本（跳过 OCR，MVP 阶段图片 URL 由前端直接上传后传入），后端持久化到 `wrong_questions` 表；分析接口同步调用 Anthropic Claude API 生成结构化诊断，写入 `ai_analyses` 表后返回。全部接口遵循 `BaseResponse[T]` 统一响应格式，每个 endpoint 先注入 RLS 变量再读写数据。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · anthropic SDK (AsyncAnthropic) · psycopg3 · pydantic v2 · pytest-asyncio STRICT · httpx (tests)

---

## File Structure

```
New files:
  backend/app/schemas/wrong_questions.py          # Pydantic 请求/响应 schema
  backend/app/services/wrong_question_service.py  # CRUD 业务逻辑（create/get/list/mastered）
  backend/app/services/ai_service.py              # Claude API 调用 + ai_analyses 写入
  backend/app/api/v1/wrong_questions.py           # 路由：6 个 endpoint
  tests/api/test_wrong_questions.py               # 全部 API 测试

Modified files:
  backend/alembic/versions/0002_add_fk_indexes.py  # 已存在，Task 0 运行并提交
  backend/app/api/v1/router.py                    # 注册 wrong_questions_router
  backend/app/core/config.py                      # 追加 anthropic_api_key 字段
  backend/.env                                    # 追加 ANTHROPIC_API_KEY=sk-ant-...
  backend/.env.example                            # 追加占位行
  backend/pyproject.toml                          # 追加 anthropic>=0.40.0
```

**Endpoint 列表：**
```
POST   /api/v1/wrong-questions/                      创建错题
GET    /api/v1/wrong-questions/                      列表（分页）
GET    /api/v1/wrong-questions/{wq_id}               单条详情
PATCH  /api/v1/wrong-questions/{wq_id}/mastered      标记已掌握
POST   /api/v1/wrong-questions/{wq_id}/analyze       触发 AI 分析
GET    /api/v1/wrong-questions/{wq_id}/analyses      查询分析历史
```

---

## Task 0: Alembic 0002 — 提交 FK 索引迁移并运行

**Files:**
- Modify (commit): `backend/alembic/versions/0002_add_fk_indexes.py`

> 此文件已存在于工作区但尚未提交。内容正确，直接提交后跑迁移。

- [ ] **Step 1: 验证文件存在**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
cat alembic/versions/0002_add_fk_indexes.py
```

Expected: 包含 `ix_wrong_questions_student_id` 等 7 个索引的 upgrade/downgrade 函数。

- [ ] **Step 2: 提交文件**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/alembic/versions/0002_add_fk_indexes.py
git commit -m "feat(alembic): 0002 add FK indexes for high-frequency query columns"
```

- [ ] **Step 3: 运行迁移**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
alembic upgrade head
```

Expected output（末行）:
```
INFO  [alembic.runtime.migration] Running upgrade 9f9152b49be9 -> 3c7d8e2f1a04, add_fk_indexes
```

- [ ] **Step 4: 确认索引已建**

```bash
python3 - <<'EOF'
import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
from app.core.database import _async_session_factory
import sqlalchemy as sa

async def main():
    async with _async_session_factory() as db:
        result = await db.execute(sa.text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'wrong_questions' AND indexname LIKE 'ix_%'"
        ))
        print([r[0] for r in result.fetchall()])

asyncio.run(main())
EOF
```

Expected: `['ix_wrong_questions_student_id']`

---

## Task 1: 依赖扩展 + Config 追加 anthropic_api_key

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env`
- Modify: `backend/.env.example`

- [ ] **Step 1: 写失败测试（config 字段不存在）**

在 `tests/api/test_wrong_questions.py` 新建文件，写第一个测试：

```python
# tests/api/test_wrong_questions.py
from app.core.config import settings


def test_settings_has_anthropic_api_key():
    """settings 必须有 anthropic_api_key 字段（值可为 placeholder）。"""
    assert hasattr(settings, "anthropic_api_key")
    assert isinstance(settings.anthropic_api_key, str)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py::test_settings_has_anthropic_api_key -v
```

Expected: `FAILED` with `AttributeError: 'Settings' object has no attribute 'anthropic_api_key'`

- [ ] **Step 3: 追加 anthropic 依赖**

修改 `backend/pyproject.toml`，在 `dependencies` 列表末尾追加：

```toml
[project]
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
]
```

- [ ] **Step 4: 安装 anthropic**

```bash
pip install "anthropic>=0.40.0"
```

Expected: `Successfully installed anthropic-...`

- [ ] **Step 5: 追加 anthropic_api_key 到 Settings**

完整替换 `backend/app/core/config.py`：

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

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
```

- [ ] **Step 6: 追加到 .env 和 .env.example**

在 `backend/.env` 末尾追加：
```
ANTHROPIC_API_KEY=sk-ant-your-real-key-here
```

在 `backend/.env.example` 末尾追加：
```
# Anthropic Claude API（AI 分析功能）
ANTHROPIC_API_KEY=your-anthropic-api-key
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py::test_settings_has_anthropic_api_key -v
```

Expected: `PASSED`

- [ ] **Step 8: 运行全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `54 passed`

- [ ] **Step 9: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/pyproject.toml backend/app/core/config.py backend/.env.example tests/api/test_wrong_questions.py
git commit -m "feat(config): add anthropic_api_key + anthropic SDK dependency"
```

> 注意：`backend/.env` 已在 `.gitignore` 中，**不要** `git add backend/.env`。

---

## Task 2: WrongQuestion Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/wrong_questions.py`
- Modify: `tests/api/test_wrong_questions.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/api/test_wrong_questions.py`：

```python
import uuid
from datetime import datetime, timezone

from app.schemas.wrong_questions import (
    AiAnalysisOut,
    MarkMasteredRequest,
    WrongQuestionCreate,
    WrongQuestionListOut,
    WrongQuestionOut,
)


def test_wrong_question_create_requires_source_image_url():
    """source_image_url 是必填项。"""
    wq = WrongQuestionCreate(source_image_url="https://cdn.example.com/img.jpg")
    assert wq.source_image_url == "https://cdn.example.com/img.jpg"
    assert wq.question_text is None
    assert wq.tags is None


def test_wrong_question_out_serializes():
    now = datetime.now(timezone.utc)
    out = WrongQuestionOut(
        id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        source_image_url="https://cdn.example.com/img.jpg",
        question_text="What is the correct tense here?",
        student_answer="I go to school yesterday",
        correct_answer="I went to school yesterday",
        question_type="单选",
        difficulty=2,
        tags=["时态", "过去式"],
        is_mastered=False,
        mastered_at=None,
        created_at=now,
        updated_at=now,
    )
    assert out.is_mastered is False
    assert out.tags == ["时态", "过去式"]


def test_ai_analysis_out_serializes():
    now = datetime.now(timezone.utc)
    out = AiAnalysisOut(
        id=str(uuid.uuid4()),
        wrong_question_id=str(uuid.uuid4()),
        llm_provider="claude",
        error_types=["时态错误"],
        knowledge_points=["一般过去时"],
        diagnosis="学生混淆了一般现在时和一般过去时。",
        suggestions="加强时态练习，重点复习过去时标志词。",
        confidence_score=0.92,
        tokens_used=312,
        created_at=now,
    )
    assert out.llm_provider == "claude"
    assert out.confidence_score == 0.92
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "schema or create_requires or out_serial" -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.schemas.wrong_questions'`

- [ ] **Step 3: 创建 schema 文件**

创建 `backend/app/schemas/wrong_questions.py`：

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── 请求体 ────────────────────────────────────────────────────────────────────


class WrongQuestionCreate(BaseModel):
    """POST /wrong-questions/ 请求体。"""

    source_image_url: str = Field(..., description="已上传的题目图片 URL（必填）")
    question_text: str | None = Field(None, description="题目文字（OCR 结果或手动录入）")
    student_answer: str | None = Field(None, description="学生作答")
    correct_answer: str | None = Field(None, description="正确答案")
    question_type: str | None = Field(
        None,
        description="题型：单选 | 完型 | 阅读 | 作文 | 其他",
    )
    difficulty: int | None = Field(None, ge=1, le=5, description="难度 1-5")
    tags: list[str] | None = Field(None, description="自定义标签列表")


class MarkMasteredRequest(BaseModel):
    """PATCH /wrong-questions/{id}/mastered 请求体。"""

    is_mastered: bool


# ── 响应体 ────────────────────────────────────────────────────────────────────


class WrongQuestionOut(BaseModel):
    id: str
    student_id: str
    source_image_url: str
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None
    difficulty: int | None
    tags: list[str] | None
    is_mastered: bool
    mastered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WrongQuestionListOut(BaseModel):
    items: list[WrongQuestionOut]
    total: int


class AiAnalysisOut(BaseModel):
    id: str
    wrong_question_id: str
    llm_provider: str
    error_types: list[str]
    knowledge_points: list[str]
    diagnosis: str
    suggestions: str
    confidence_score: float | None
    tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "schema or create_requires or out_serial or analysis_out" -v
```

Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/wrong_questions.py tests/api/test_wrong_questions.py
git commit -m "feat(schemas): WrongQuestion + AiAnalysis Pydantic schemas"
```

---

## Task 3: WrongQuestion CRUD Service

**Files:**
- Create: `backend/app/services/wrong_question_service.py`
- Modify: `tests/api/test_wrong_questions.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/api/test_wrong_questions.py`：

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import WrongQuestion, AiAnalysis
from app.schemas.wrong_questions import WrongQuestionCreate
from app.services.wrong_question_service import (
    create_wrong_question,
    get_wrong_question,
    list_wrong_questions,
    mark_mastered,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_student(db_session):
    """在 DB 中创建一个测试用 student User。"""
    from app.services.auth_service import upsert_user
    user = await upsert_user(db_session, openid=f"wq_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_create_wrong_question(db_session, test_student):
    data = WrongQuestionCreate(
        source_image_url="https://cdn.example.com/test.jpg",
        question_text="She __ to school every day.",
        student_answer="go",
        correct_answer="goes",
        question_type="单选",
        difficulty=2,
        tags=["主谓一致"],
    )
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    assert wq.id is not None
    assert wq.student_id == test_student.id
    assert wq.question_text == "She __ to school every day."
    assert wq.tags == ["主谓一致"]
    assert wq.is_mastered is False


@pytest.mark.asyncio
async def test_get_wrong_question_owned(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/a.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    found = await get_wrong_question(db_session, wq_id=wq.id, student_id=test_student.id)
    assert found is not None
    assert found.id == wq.id


@pytest.mark.asyncio
async def test_get_wrong_question_not_owned_returns_none(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/b.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    other_id = uuid.uuid4()
    found = await get_wrong_question(db_session, wq_id=wq.id, student_id=other_id)
    assert found is None


@pytest.mark.asyncio
async def test_list_wrong_questions(db_session, test_student):
    for i in range(3):
        await create_wrong_question(
            db_session,
            student_id=test_student.id,
            data=WrongQuestionCreate(source_image_url=f"https://cdn.example.com/{i}.jpg"),
        )
    items, total = await list_wrong_questions(
        db_session, student_id=test_student.id, skip=0, limit=10
    )
    assert total >= 3
    assert len(items) >= 3


@pytest.mark.asyncio
async def test_mark_mastered(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/c.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    updated = await mark_mastered(db_session, wq=wq, is_mastered=True)
    assert updated.is_mastered is True
    assert updated.mastered_at is not None
    un = await mark_mastered(db_session, wq=updated, is_mastered=False)
    assert un.is_mastered is False
    assert un.mastered_at is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "create_wrong or get_wrong or list_wrong or mark_master" -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.services.wrong_question_service'`

- [ ] **Step 3: 创建 CRUD service**

创建 `backend/app/services/wrong_question_service.py`：

```python
"""错题 CRUD 业务逻辑。

所有函数使用 db.flush()，由 endpoint 层控制 commit。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.schemas.wrong_questions import WrongQuestionCreate


async def create_wrong_question(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    data: WrongQuestionCreate,
) -> WrongQuestion:
    """创建错题记录，返回已 flush 的 ORM 对象（调用方需 commit）。"""
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_url=data.source_image_url,
        question_text=data.question_text,
        student_answer=data.student_answer,
        correct_answer=data.correct_answer,
        question_type=data.question_type,
        difficulty=data.difficulty,
        tags=data.tags,
    )
    db.add(wq)
    await db.flush()
    return wq


async def get_wrong_question(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
    student_id: uuid.UUID,
) -> WrongQuestion | None:
    """按 id + student_id 查询（student_id 防止越权访问）。"""
    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.id == wq_id)
        .where(WrongQuestion.student_id == student_id)
    )
    return result.scalar_one_or_none()


async def list_wrong_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[WrongQuestion], int]:
    """分页查询当前学生的错题，按创建时间倒序，返回 (items, total)。"""
    count_result = await db.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == student_id
        )
    )
    total: int = count_result.scalar_one()

    rows = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.student_id == student_id)
        .order_by(WrongQuestion.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(rows.scalars().all()), total


async def mark_mastered(
    db: AsyncSession,
    *,
    wq: WrongQuestion,
    is_mastered: bool,
) -> WrongQuestion:
    """切换已掌握状态；is_mastered=True 时记录 mastered_at。"""
    wq.is_mastered = is_mastered
    wq.mastered_at = datetime.now(timezone.utc) if is_mastered else None
    await db.flush()
    return wq


async def list_analyses(
    db: AsyncSession,
    *,
    wrong_question_id: uuid.UUID,
) -> list[AiAnalysis]:
    """查询某道错题的全部 AI 分析记录，按创建时间倒序。"""
    rows = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.wrong_question_id == wrong_question_id)
        .order_by(AiAnalysis.created_at.desc())
    )
    return list(rows.scalars().all())
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "create_wrong or get_wrong or list_wrong or mark_master" -v
```

Expected: `5 passed`

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `59 passed` (原 54 + 5 新增)

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/wrong_question_service.py tests/api/test_wrong_questions.py
git commit -m "feat(service): wrong_question CRUD — create/get/list/mark_mastered/list_analyses"
```

---

## Task 4: WrongQuestion API Endpoints（create + list + get + mastered）

**Files:**
- Create: `backend/app/api/v1/wrong_questions.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_wrong_questions.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/api/test_wrong_questions.py`：

```python
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """获取测试用 access token（通过 mock 微信登录）。"""
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"wq_api_test_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_wrong_question_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/test.jpg",
            "question_text": "She __ to school every day.",
            "student_answer": "go",
            "correct_answer": "goes",
            "question_type": "单选",
            "difficulty": 2,
            "tags": ["主谓一致"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["question_type"] == "单选"
    assert body["data"]["is_mastered"] is False
    assert body["data"]["id"] != ""


@pytest.mark.asyncio
async def test_create_wrong_question_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/test.jpg"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_wrong_questions_api(client: AsyncClient, auth_headers):
    # 先创建两条
    for i in range(2):
        await client.post(
            "/api/v1/wrong-questions/",
            json={"source_image_url": f"https://cdn.example.com/{i}.jpg"},
            headers=auth_headers,
        )
    resp = await client.get("/api/v1/wrong-questions/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] >= 2
    assert isinstance(body["data"]["items"], list)


@pytest.mark.asyncio
async def test_get_wrong_question_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/get_test.jpg"},
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/wrong-questions/{wq_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == wq_id


@pytest.mark.asyncio
async def test_get_wrong_question_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(
        f"/api/v1/wrong-questions/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_mastered_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/mastered.jpg"},
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]
    resp = await client.patch(
        f"/api/v1/wrong-questions/{wq_id}/mastered",
        json={"is_mastered": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_mastered"] is True
    assert resp.json()["data"]["mastered_at"] is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "api" -v 2>&1 | head -20
```

Expected: `FAILED` 含 `404 Not Found` (router 未注册)

- [ ] **Step 3: 创建路由文件**

创建 `backend/app/api/v1/wrong_questions.py`：

```python
"""错题 CRUD API。

所有 endpoint 需要 Bearer JWT，并注入 RLS 变量。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.wrong_questions import (
    AiAnalysisOut,
    MarkMasteredRequest,
    WrongQuestionCreate,
    WrongQuestionListOut,
    WrongQuestionOut,
)
from app.services import wrong_question_service

router = APIRouter(prefix="/wrong-questions", tags=["wrong-questions"])

# ── 依赖别名 ──────────────────────────────────────────────────────────────────

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/", response_model=BaseResponse[WrongQuestionOut])
async def create_wrong_question(
    body: WrongQuestionCreate,
    db: DbDep,
    current_user: UserDep,
):
    """提交新错题（MVP：前端先上传图片到 OSS，再传 URL）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.create_wrong_question(
        db, student_id=current_user.id, data=body
    )
    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))


@router.get("/", response_model=BaseResponse[WrongQuestionListOut])
async def list_wrong_questions(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """获取当前学生的错题列表（分页，按创建时间倒序）。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await wrong_question_service.list_wrong_questions(
        db, student_id=current_user.id, skip=skip, limit=limit
    )
    return make_ok(
        WrongQuestionListOut(
            items=[WrongQuestionOut.model_validate(wq) for wq in items],
            total=total,
        )
    )


@router.get("/{wq_id}", response_model=BaseResponse[WrongQuestionOut])
async def get_wrong_question(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """获取单条错题详情（只能查自己的）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    return make_ok(WrongQuestionOut.model_validate(wq))


@router.patch("/{wq_id}/mastered", response_model=BaseResponse[WrongQuestionOut])
async def mark_mastered(
    wq_id: uuid.UUID,
    body: MarkMasteredRequest,
    db: DbDep,
    current_user: UserDep,
):
    """标记/取消已掌握。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    wq = await wrong_question_service.mark_mastered(db, wq=wq, is_mastered=body.is_mastered)
    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))


@router.post("/{wq_id}/analyze", response_model=BaseResponse[AiAnalysisOut])
async def analyze_wrong_question(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """触发 AI 分析（同步，约 3-8 秒）。每次调用生成新的分析记录。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    from app.services import ai_service  # 延迟导入，避免启动时加载 anthropic

    analysis = await ai_service.analyze_wrong_question(db, wq=wq, student_id=current_user.id)
    await db.commit()
    await db.refresh(analysis)
    return make_ok(AiAnalysisOut.model_validate(analysis))


@router.get("/{wq_id}/analyses", response_model=BaseResponse[list[AiAnalysisOut]])
async def list_analyses(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查询某道错题的全部 AI 分析历史。"""
    await get_rls_db(db, str(current_user.id))
    # 先验证该错题归属当前用户
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    analyses = await wrong_question_service.list_analyses(db, wrong_question_id=wq_id)
    return make_ok([AiAnalysisOut.model_validate(a) for a in analyses])
```

- [ ] **Step 4: 注册路由**

修改 `backend/app/api/v1/router.py`：

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.wrong_questions import router as wrong_questions_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(wrong_questions_router)
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "api and not analyze" -v
```

Expected: `7 passed`（create + auth_required + list + get + not_found + mastered + mastered 包含各自变体）

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `66 passed`（54 + 5 + 7 新增）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/wrong_questions.py backend/app/api/v1/router.py tests/api/test_wrong_questions.py
git commit -m "feat(api): wrong-questions CRUD — POST/GET/PATCH with JWT + RLS"
```

---

## Task 5: AI 分析 Service（调用 Claude API）

**Files:**
- Create: `backend/app/services/ai_service.py`
- Modify: `tests/api/test_wrong_questions.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/api/test_wrong_questions.py`：

```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_analyze_wrong_question_service(db_session, test_student):
    """ai_service.analyze_wrong_question 应写入 AiAnalysis 并返回对象。"""
    from app.services.ai_service import analyze_wrong_question
    from app.models.d3_wrong_questions import AiAnalysis

    # 先创建一道错题
    data = WrongQuestionCreate(
        source_image_url="https://cdn.example.com/svc_test.jpg",
        question_text="He don't like apples.",
        student_answer="don't",
        correct_answer="doesn't",
        question_type="单选",
    )
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)

    # mock Anthropic 返回
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = (
        '{"error_types": ["主谓一致错误"], "knowledge_points": ["第三人称单数助动词"], '
        '"diagnosis": "学生对第三人称单数助动词使用错误。", '
        '"suggestions": "复习主谓一致规则，重点记忆 does/doesn\'t。", '
        '"confidence_score": 0.95}'
    )
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 80

    with patch("app.services.ai_service.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        analysis = await analyze_wrong_question(
            db_session, wq=wq, student_id=test_student.id
        )

    assert analysis.llm_provider == "claude"
    assert analysis.error_types == ["主谓一致错误"]
    assert analysis.knowledge_points == ["第三人称单数助动词"]
    assert analysis.tokens_used == 280
    assert analysis.confidence_score == 0.95
    assert analysis.wrong_question_id == wq.id
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py::test_analyze_wrong_question_service -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.services.ai_service'`

- [ ] **Step 3: 创建 AI service**

创建 `backend/app/services/ai_service.py`：

```python
"""AI 分析服务：调用 Anthropic Claude API 生成英语错题诊断报告。

- 使用 AsyncAnthropic（异步 client）。
- LLM 返回 JSON 字符串，解析后写入 ai_analyses 表。
- 调用方需 await db.commit() 才真正落库。
"""
from __future__ import annotations

import json
import uuid

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion

_SYSTEM_PROMPT = (
    "你是一个专业的英语教学诊断助手，擅长分析英语错题并给出结构化诊断报告。"
    "请严格按照 JSON 格式输出，不要有任何其他文字。"
)

_USER_PROMPT_TEMPLATE = """请分析以下英语错题，给出诊断报告。

题目内容: {question_text}
学生答案: {student_answer}
正确答案: {correct_answer}
题型: {question_type}

请以纯 JSON 格式返回（不要任何 markdown 代码块或额外文字）:
{{
  "error_types": ["错误类型1", "错误类型2"],
  "knowledge_points": ["涉及知识点1", "涉及知识点2"],
  "diagnosis": "详细诊断说明（2-3句话，指出错误原因）",
  "suggestions": "学习建议（2-3句话，给出提升方向）",
  "confidence_score": 0.85
}}"""


async def analyze_wrong_question(
    db: AsyncSession,
    *,
    wq: WrongQuestion,
    student_id: uuid.UUID,
) -> AiAnalysis:
    """调用 Claude API 分析错题，写入 ai_analyses 表，返回 ORM 对象（未 commit）。

    异常处理：
    - Anthropic API 错误 → AppError(502, "AI服务暂时不可用，请稍后重试")
    - JSON 解析失败   → AppError(500, "AI分析返回格式异常")
    """
    prompt = _USER_PROMPT_TEMPLATE.format(
        question_text=wq.question_text or "(暂无文字内容)",
        student_answer=wq.student_answer or "(未提供)",
        correct_answer=wq.correct_answer or "(未提供)",
        question_type=wq.question_type or "未知",
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc

    raw_text = response.content[0].text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI分析返回格式异常") from exc

    analysis = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq.id,
        student_id=student_id,
        llm_provider="claude",
        error_types=data.get("error_types", []),
        knowledge_points=data.get("knowledge_points", []),
        diagnosis=data["diagnosis"],
        suggestions=data["suggestions"],
        confidence_score=data.get("confidence_score"),
        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
    )
    db.add(analysis)
    await db.flush()
    return analysis
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py::test_analyze_wrong_question_service -v
```

Expected: `PASSED`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `67 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/ai_service.py tests/api/test_wrong_questions.py
git commit -m "feat(service): AI analysis service — Claude API + structured diagnosis"
```

---

## Task 6: 分析 API Endpoints（analyze + list analyses）

**Files:**
- Modify: `tests/api/test_wrong_questions.py`

> `wrong_questions.py` 路由已在 Task 4 中实现了 `POST /{id}/analyze` 和 `GET /{id}/analyses`。本 Task 只需补充 API 集成测试。

- [ ] **Step 1: 写失败测试**

追加到 `tests/api/test_wrong_questions.py`：

```python
@pytest.mark.asyncio
async def test_analyze_endpoint(client: AsyncClient, auth_headers):
    """POST /wrong-questions/{id}/analyze 应返回 AiAnalysisOut。"""
    # 创建错题
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/analyze_test.jpg",
            "question_text": "She don't like coffee.",
            "student_answer": "don't",
            "correct_answer": "doesn't",
            "question_type": "单选",
        },
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]

    # mock Claude API
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = (
        '{"error_types": ["主谓一致"], "knowledge_points": ["does/doesn\'t"], '
        '"diagnosis": "主谓不一致错误。", "suggestions": "复习第三人称单数。", '
        '"confidence_score": 0.9}'
    )
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 150
    mock_response.usage.output_tokens = 60

    with patch("app.services.ai_service.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        resp = await client.post(
            f"/api/v1/wrong-questions/{wq_id}/analyze", headers=auth_headers
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["llm_provider"] == "claude"
    assert body["data"]["error_types"] == ["主谓一致"]
    assert body["data"]["tokens_used"] == 210
    assert body["data"]["wrong_question_id"] == wq_id


@pytest.mark.asyncio
async def test_analyze_not_found(client: AsyncClient, auth_headers):
    """不存在的 wq_id → 404。"""
    resp = await client.post(
        f"/api/v1/wrong-questions/{uuid.uuid4()}/analyze", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_analyses_endpoint(client: AsyncClient, auth_headers):
    """GET /wrong-questions/{id}/analyses 返回分析列表。"""
    # 创建错题
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/analyses_test.jpg",
            "question_text": "I has a dog.",
            "student_answer": "has",
            "correct_answer": "have",
        },
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]

    # 调用两次分析
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = (
        '{"error_types": ["助动词错误"], "knowledge_points": ["have/has"], '
        '"diagnosis": "主谓一致错误。", "suggestions": "复习助动词。", '
        '"confidence_score": 0.88}'
    )
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    with patch("app.services.ai_service.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        for _ in range(2):
            await client.post(
                f"/api/v1/wrong-questions/{wq_id}/analyze", headers=auth_headers
            )

    resp = await client.get(
        f"/api/v1/wrong-questions/{wq_id}/analyses", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert len(body["data"]) == 2
```

- [ ] **Step 2: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_wrong_questions.py -k "analyze or list_analyses" -v
```

Expected: `4 passed`（1 service + 3 新 API 测试）

- [ ] **Step 3: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `70 passed`

- [ ] **Step 4: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add tests/api/test_wrong_questions.py
git commit -m "test(api): AI analysis endpoint tests — analyze + list analyses"
```

---

## Task 7: 集成验证 + Push + 归档 D-061

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -20
```

Expected: 全部 PASS（≥70 个测试）

- [ ] **Step 2: 启动 uvicorn，手动验证关键端点**

```bash
uvicorn app.main:app --port 8003 --log-level warning &
sleep 3

# 1. 健康检查
curl -s http://localhost:8003/health | python3 -m json.tool

# 2. 无 token 访问 wrong-questions → 401
curl -s http://localhost:8003/api/v1/wrong-questions/ | python3 -m json.tool

# 3. 不存在的错题 → 404（需先登录，用 test token）
```

Expected `/health`: `{"status": "ok"}`
Expected 无 token: HTTP 401 `{"detail": "未授权，请重新登录"}`

- [ ] **Step 3: 确认 /docs 正常显示新路由**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/docs
```

Expected: `200`

在浏览器打开 http://localhost:8003/docs，确认 `wrong-questions` 分组下有 6 个端点。

- [ ] **Step 4: 停止 uvicorn**

```bash
pkill -f "uvicorn app.main:app"
```

- [ ] **Step 5: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 6: 追加 D-061 到决策归档**

在 `docs/决策归档.md` 的 `## D-060` 段落之前插入：

```markdown
## D-061｜错题提交 + AI 分析 MVP：Tasks 0-7 全量交付

**日期：** 2026-05-26
**背景：** FastAPI auth 层完成后，下一步实现 MVP 核心功能——学生提交错题、触发 AI 诊断、查询报告。
**结论：**
1. **Alembic 0002（Task 0）：** 提交并运行 FK 索引迁移，覆盖 7 张高频查询表。
2. **Anthropic SDK（Task 1）：** 追加 `anthropic>=0.40.0` 依赖；`Settings.anthropic_api_key` 从 .env 读取，默认 placeholder。
3. **WrongQuestion Schemas（Task 2）：** `WrongQuestionCreate`（source_image_url 必填）、`WrongQuestionOut`、`WrongQuestionListOut`、`AiAnalysisOut`、`MarkMasteredRequest`。
4. **CRUD Service（Task 3）：** `create/get/list/mark_mastered/list_analyses`，均用 `db.flush()`，调用方控制事务边界。
5. **CRUD API（Task 4）：** POST/GET list/GET one/PATCH mastered，全部 Bearer + RLS 注入；404 用 `AppError(404)`。
6. **AI Service（Task 5）：** `AsyncAnthropic`，提示词要求 JSON 输出；API 异常→502，JSON 解析失败→500；结构化写入 `ai_analyses`。
7. **分析 API（Task 6）：** POST /{id}/analyze 同步触发分析；GET /{id}/analyses 按创建时间倒序返回历史。
8. **MVP 设计决策：** OCR 流程跳过（MVP 阶段图片 URL 由前端上传后直传），source_image_url 保持 NOT NULL；分析同步返回（非队列），约 3-8 秒；每次调用生成新的分析记录（支持多次分析同一道题）。
**影响范围：** `backend/app/services/ai_service.py` + `wrong_question_service.py` + `app/api/v1/wrong_questions.py` + schemas；共 ≥70 个测试全部通过；已推送 GitHub main 分支。

---
```

- [ ] **Step 7: 提交归档**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-061 — wrong-questions + AI analysis MVP complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | 对应 Task |
|------|-----------|
| 提交错题（含图片 URL） | Task 4 POST /wrong-questions/ |
| 列表查询（分页） | Task 4 GET /wrong-questions/ |
| 单条详情 | Task 4 GET /wrong-questions/{id} |
| 标记已掌握 | Task 4 PATCH /{id}/mastered |
| AI 诊断触发 | Task 5+6 POST /{id}/analyze |
| 查询分析历史 | Task 6 GET /{id}/analyses |
| 越权访问防护 | Task 3/4 student_id 双重过滤 + RLS 注入 |
| FK 索引性能 | Task 0 Alembic 0002 |
| 统一响应格式 | 全部 endpoint 使用 BaseResponse[T] |

### 2. Placeholder 扫描

- 无 TBD/TODO/implement later
- 每个 Step 均含完整代码或明确命令
- 所有 schema、service、endpoint 代码完整展示

### 3. 类型一致性

- `WrongQuestionOut.model_validate(wq)` — ORM→Pydantic 使用 `from_attributes=True` ✅
- `AiAnalysisOut.model_validate(analysis)` — 同上 ✅
- `mark_mastered(db, wq=wq, is_mastered=body.is_mastered)` — 参数名与 Task 3 service 函数签名一致 ✅
- `analyze_wrong_question(db, wq=wq, student_id=current_user.id)` — 与 Task 5 service 签名一致 ✅
- `list_analyses(db, wrong_question_id=wq_id)` — 与 Task 3 service 签名一致 ✅
