# 学情诊断报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `GET /api/v1/diagnosis/report`，聚合学生所有错题和 AI 分析数据，返回错误类型分布、知识点薄弱项、题型/难度分布、近30天活跃度等结构化学情报告。

**Architecture:** 服务层直接查询 `wrong_questions`（by student_id）和 `ai_analyses`（by student_id，无需 JOIN），用 Python `collections.Counter` 做内存聚合，返回 Pydantic schema；数据量 MVP 阶段（单用户 < 1000 条）内存聚合够用。Endpoint 走 Bearer + RLS 注入，与现有鉴权模式完全一致。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · pydantic v2 · pytest-asyncio STRICT

---

## File Structure

```
New files:
  backend/app/schemas/diagnosis.py          # DiagnosisReport + 子结构 schema
  backend/app/services/diagnosis_service.py # 聚合逻辑：get_diagnosis_report()
  backend/app/api/v1/diagnosis.py           # GET /diagnosis/report endpoint
  tests/api/test_diagnosis.py              # 全部诊断报告测试

Modified files:
  backend/app/api/v1/router.py              # 注册 diagnosis_router
```

**Endpoint:**
```
GET  /api/v1/diagnosis/report   Bearer JWT 必须；返回 BaseResponse[DiagnosisReport]
```

**Key model facts（读代码前确认）：**
- `WrongQuestion.student_id` — UUID
- `WrongQuestion.question_type` — enum str: "单选"/"完型"/"阅读"/"作文"/"其他"（可为 None）
- `WrongQuestion.difficulty` — SmallInteger 1-5（可为 None）
- `WrongQuestion.is_mastered` — Boolean（非 mastered_at）
- `AiAnalysis.student_id` — UUID（可直接 by student_id 查，无需 JOIN）
- `AiAnalysis.error_types` — JSONB（Python `list[str]`）
- `AiAnalysis.knowledge_points` — JSONB（Python `list[str]`）
- `AiAnalysis.suggestions` — Text（单条字符串）

---

## Task 0: Diagnosis Schemas

**Files:**
- Create: `backend/app/schemas/diagnosis.py`
- Create: `tests/api/test_diagnosis.py`

- [ ] **Step 1: 创建 `tests/api/test_diagnosis.py` 并写失败测试**

```python
from app.schemas.diagnosis import (
    DailyActivity,
    DiagnosisReport,
    ErrorTypeCount,
    KnowledgePointCount,
)


def test_error_type_count_schema():
    etc = ErrorTypeCount(error_type="语法错误", count=5)
    assert etc.error_type == "语法错误"
    assert etc.count == 5


def test_knowledge_point_count_schema():
    kpc = KnowledgePointCount(knowledge_point="现在完成时", count=3)
    assert kpc.knowledge_point == "现在完成时"
    assert kpc.count == 3


def test_daily_activity_schema():
    da = DailyActivity(date="2026-05-26", count=3)
    assert da.date == "2026-05-26"
    assert da.count == 3


def test_diagnosis_report_schema_empty():
    report = DiagnosisReport(
        total_questions=0,
        total_analyzed=0,
        mastered_count=0,
        mastery_rate=0.0,
        top_error_types=[],
        top_weak_knowledge_points=[],
        question_type_distribution={},
        difficulty_distribution={},
        recent_daily_activity=[],
        top_suggestions=[],
    )
    assert report.total_questions == 0
    assert report.mastery_rate == 0.0
    assert report.top_error_types == []


def test_diagnosis_report_schema_with_data():
    report = DiagnosisReport(
        total_questions=10,
        total_analyzed=8,
        mastered_count=3,
        mastery_rate=0.3,
        top_error_types=[ErrorTypeCount(error_type="语法错误", count=4)],
        top_weak_knowledge_points=[KnowledgePointCount(knowledge_point="现在完成时", count=3)],
        question_type_distribution={"单选": 5, "完型": 3, "阅读": 2},
        difficulty_distribution={3: 6, 4: 4},
        recent_daily_activity=[DailyActivity(date="2026-05-26", count=2)],
        top_suggestions=["建议多练习时态题"],
    )
    assert report.total_analyzed == 8
    assert report.mastery_rate == 0.3
    assert report.top_error_types[0].error_type == "语法错误"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.schemas.diagnosis'`

- [ ] **Step 3: 创建 `backend/app/schemas/diagnosis.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorTypeCount(BaseModel):
    error_type: str
    count: int


class KnowledgePointCount(BaseModel):
    knowledge_point: str
    count: int


class DailyActivity(BaseModel):
    date: str = Field(..., description="ISO 日期，如 '2026-05-26'")
    count: int


class DiagnosisReport(BaseModel):
    """学情诊断报告。

    基于当前学生所有错题及 AI 分析结果聚合生成。
    """

    # ── 总览 ──────────────────────────────────────────────────────────────────
    total_questions: int = Field(..., description="累计提交错题数")
    total_analyzed: int = Field(..., description="已完成 AI 分析的错题数")
    mastered_count: int = Field(..., description="已标记掌握的错题数")
    mastery_rate: float = Field(..., description="掌握率 = mastered_count / total_questions")

    # ── 错误类型分布（前10，按频次降序）──────────────────────────────────────
    top_error_types: list[ErrorTypeCount]

    # ── 知识点薄弱项（前10，按出现频次降序）─────────────────────────────────
    top_weak_knowledge_points: list[KnowledgePointCount]

    # ── 题型分布 ──────────────────────────────────────────────────────────────
    question_type_distribution: dict[str, int] = Field(
        ..., description="键=题型, 值=数量"
    )

    # ── 难度分布 ──────────────────────────────────────────────────────────────
    difficulty_distribution: dict[int, int] = Field(
        ..., description="键=难度(1-5), 值=数量"
    )

    # ── 近30天每日错题提交数 ─────────────────────────────────────────────────
    recent_daily_activity: list[DailyActivity] = Field(
        ..., description="长度固定为30，从30天前到今日"
    )

    # ── 综合建议（最近5条不重复 AI 建议）────────────────────────────────────
    top_suggestions: list[str] = Field(
        ..., description="最近5条不重复的 AI 分析建议"
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -v
```

Expected: `5 passed`

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `111 passed`（106 + 5 新增）

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/diagnosis.py tests/api/test_diagnosis.py
git commit -m "feat(schemas): diagnosis report schema — ErrorTypeCount/KnowledgePointCount/DiagnosisReport"
```

---

## Task 1: Diagnosis Service

**Files:**
- Create: `backend/app/services/diagnosis_service.py`
- Modify: `tests/api/test_diagnosis.py` (append)

- [ ] **Step 1: 追加失败测试到 `tests/api/test_diagnosis.py`**

先 READ `tests/api/test_diagnosis.py` 末尾再追加（勿覆盖）：

```python
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services.diagnosis_service import get_diagnosis_report


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_student(db_session):
    from app.services.auth_service import upsert_user
    user = await upsert_user(db_session, openid=f"diag_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_get_diagnosis_report_empty(db_session, test_student):
    """无错题时返回全零报告，recent_daily_activity 固定30天。"""
    report = await get_diagnosis_report(db_session, student_id=test_student.id)
    assert report.total_questions == 0
    assert report.total_analyzed == 0
    assert report.mastered_count == 0
    assert report.mastery_rate == 0.0
    assert report.top_error_types == []
    assert report.top_weak_knowledge_points == []
    assert report.question_type_distribution == {}
    assert report.difficulty_distribution == {}
    assert len(report.recent_daily_activity) == 30
    assert report.top_suggestions == []


@pytest.mark.asyncio
async def test_get_diagnosis_report_with_data(db_session, test_student):
    """有错题+分析时，聚合结果正确。"""
    from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion

    # 创建2道错题
    wq1 = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img1.jpg",
        question_type="单选",
        difficulty=3,
        is_mastered=True,
    )
    wq2 = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img2.jpg",
        question_type="完型",
        difficulty=4,
        is_mastered=False,
    )
    db_session.add_all([wq1, wq2])
    await db_session.flush()

    # 为 wq1 创建 AI 分析
    analysis = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq1.id,
        student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误", "时态错误"],
        knowledge_points=["现在完成时", "过去时"],
        diagnosis="该生对时态掌握不牢。",
        suggestions="建议复习时态用法，多做专项练习。",
        confidence_score=0.85,
        tokens_used=512,
    )
    db_session.add(analysis)
    await db_session.flush()

    report = await get_diagnosis_report(db_session, student_id=test_student.id)

    assert report.total_questions == 2
    assert report.total_analyzed == 1
    assert report.mastered_count == 1
    assert report.mastery_rate == 0.5
    assert len(report.top_error_types) == 2
    assert {etc.error_type for etc in report.top_error_types} == {"语法错误", "时态错误"}
    assert len(report.top_weak_knowledge_points) == 2
    assert report.question_type_distribution == {"单选": 1, "完型": 1}
    assert report.difficulty_distribution == {3: 1, 4: 1}
    assert len(report.recent_daily_activity) == 30
    assert len(report.top_suggestions) == 1
    assert report.top_suggestions[0] == "建议复习时态用法，多做专项练习。"


@pytest.mark.asyncio
async def test_get_diagnosis_report_error_type_ordering(db_session, test_student):
    """error_types 按频次降序排列。"""
    from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion

    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    # 分析1：语法错误 + 词汇错误
    a1 = AiAnalysis(
        id=uuid.uuid4(), wrong_question_id=wq.id, student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误", "词汇错误"],
        knowledge_points=["介词"],
        diagnosis="d", suggestions="s1",
        confidence_score=0.8, tokens_used=100,
    )
    # 分析2：语法错误（重复出现）
    wq2 = WrongQuestion(
        id=uuid.uuid4(), student_id=test_student.id,
        source_image_url="https://example.com/img2.jpg", is_mastered=False,
    )
    db_session.add(wq2)
    await db_session.flush()
    a2 = AiAnalysis(
        id=uuid.uuid4(), wrong_question_id=wq2.id, student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误"],
        knowledge_points=["主谓一致"],
        diagnosis="d2", suggestions="s2",
        confidence_score=0.9, tokens_used=80,
    )
    db_session.add_all([a1, a2])
    await db_session.flush()

    report = await get_diagnosis_report(db_session, student_id=test_student.id)

    # 语法错误出现2次，应排第一
    assert report.top_error_types[0].error_type == "语法错误"
    assert report.top_error_types[0].count == 2
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -k "diagnosis_report_empty or with_data or ordering" -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.services.diagnosis_service'`

- [ ] **Step 3: 创建 `backend/app/services/diagnosis_service.py`**

```python
"""学情诊断报告业务逻辑。

策略：
- 直接按 student_id 查询 wrong_questions 和 ai_analyses（无需 JOIN）。
- 内存聚合（Counter）—— MVP 阶段单用户数据量 < 1000 条，够用。
- recent_daily_activity 固定返回最近30天（含今日），无数据日期 count=0。
- top_suggestions：最近5条不重复（按 AiAnalysis.created_at 倒序）。
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.schemas.diagnosis import (
    DailyActivity,
    DiagnosisReport,
    ErrorTypeCount,
    KnowledgePointCount,
)

_TOP_N = 10          # error_types / knowledge_points 取前10
_SUGGESTION_N = 5    # 最多返回5条建议
_ACTIVITY_DAYS = 30  # 近30天活跃度


async def get_diagnosis_report(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> DiagnosisReport:
    """聚合学生学情数据，返回诊断报告。只读，不修改数据库。"""

    # ── 1. 加载数据 ──────────────────────────────────────────────────────────
    wqs_result = await db.execute(
        select(WrongQuestion).where(WrongQuestion.student_id == student_id)
    )
    wqs: list[WrongQuestion] = list(wqs_result.scalars().all())

    analyses_result = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.student_id == student_id)
        .order_by(AiAnalysis.created_at.desc())
    )
    analyses: list[AiAnalysis] = list(analyses_result.scalars().all())

    # ── 2. 总览 ──────────────────────────────────────────────────────────────
    total_questions = len(wqs)
    mastered_count = sum(1 for wq in wqs if wq.is_mastered)
    mastery_rate = round(mastered_count / total_questions, 4) if total_questions > 0 else 0.0

    analyzed_wq_ids = {a.wrong_question_id for a in analyses}
    total_analyzed = len(analyzed_wq_ids)

    # ── 3. 错误类型 & 知识点（Counter 聚合）──────────────────────────────────
    error_type_counter: Counter[str] = Counter()
    kp_counter: Counter[str] = Counter()

    for a in analyses:
        if a.error_types:
            error_type_counter.update(a.error_types)
        if a.knowledge_points:
            kp_counter.update(a.knowledge_points)

    top_error_types = [
        ErrorTypeCount(error_type=et, count=c)
        for et, c in error_type_counter.most_common(_TOP_N)
    ]
    top_weak_knowledge_points = [
        KnowledgePointCount(knowledge_point=kp, count=c)
        for kp, c in kp_counter.most_common(_TOP_N)
    ]

    # ── 4. 题型 & 难度分布 ────────────────────────────────────────────────────
    question_type_distribution: dict[str, int] = {}
    difficulty_distribution: dict[int, int] = {}

    for wq in wqs:
        if wq.question_type is not None:
            question_type_distribution[wq.question_type] = (
                question_type_distribution.get(wq.question_type, 0) + 1
            )
        if wq.difficulty is not None:
            difficulty_distribution[wq.difficulty] = (
                difficulty_distribution.get(wq.difficulty, 0) + 1
            )

    # ── 5. 近30天每日活跃度 ──────────────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=_ACTIVITY_DAYS - 1)

    daily_counts: dict[str, int] = {}
    for wq in wqs:
        wq_date = wq.created_at.date()
        if wq_date >= start_date:
            key = wq_date.isoformat()
            daily_counts[key] = daily_counts.get(key, 0) + 1

    recent_daily_activity = [
        DailyActivity(
            date=(start_date + timedelta(days=i)).isoformat(),
            count=daily_counts.get((start_date + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(_ACTIVITY_DAYS)
    ]

    # ── 6. 综合建议（最近5条不重复）─────────────────────────────────────────
    seen_suggestions: set[str] = set()
    top_suggestions: list[str] = []
    for a in analyses:                           # 已按 created_at DESC 排序
        s = (a.suggestions or "").strip()
        if s and s not in seen_suggestions:
            seen_suggestions.add(s)
            top_suggestions.append(s)
        if len(top_suggestions) >= _SUGGESTION_N:
            break

    return DiagnosisReport(
        total_questions=total_questions,
        total_analyzed=total_analyzed,
        mastered_count=mastered_count,
        mastery_rate=mastery_rate,
        top_error_types=top_error_types,
        top_weak_knowledge_points=top_weak_knowledge_points,
        question_type_distribution=question_type_distribution,
        difficulty_distribution=difficulty_distribution,
        recent_daily_activity=recent_daily_activity,
        top_suggestions=top_suggestions,
    )
```

- [ ] **Step 4: 运行目标测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -k "diagnosis_report_empty or with_data or ordering" -v
```

Expected: `3 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `114 passed`（111 + 3 新增）

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/diagnosis_service.py tests/api/test_diagnosis.py
git commit -m "feat(service): diagnosis report — aggregate error types, knowledge points, activity"
```

---

## Task 2: API Endpoint + Router

**Files:**
- Create: `backend/app/api/v1/diagnosis.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_diagnosis.py` (append)

- [ ] **Step 1: 追加 API 集成测试**

追加到 `tests/api/test_diagnosis.py`（READ 当前末尾后再追加）：

```python
import unittest.mock
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
        mock_wx.return_value = {"openid": f"diag_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_requires_auth(client: AsyncClient):
    """未登录返回 401。"""
    resp = await client.get("/api/v1/diagnosis/report")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_empty(client: AsyncClient, auth_headers):
    """新用户无数据时，返回全零报告 + 30天活跃度数组。"""
    resp = await client.get("/api/v1/diagnosis/report", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total_questions"] == 0
    assert data["total_analyzed"] == 0
    assert data["mastered_count"] == 0
    assert data["mastery_rate"] == 0.0
    assert data["top_error_types"] == []
    assert data["top_weak_knowledge_points"] == []
    assert data["question_type_distribution"] == {}
    assert len(data["recent_daily_activity"]) == 30
    assert data["top_suggestions"] == []


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_structure(client: AsyncClient, auth_headers):
    """响应结构正确：所有字段存在，类型正确。"""
    resp = await client.get("/api/v1/diagnosis/report", headers=auth_headers)
    data = resp.json()["data"]
    # 所有必需字段存在
    assert "total_questions" in data
    assert "total_analyzed" in data
    assert "mastered_count" in data
    assert "mastery_rate" in data
    assert "top_error_types" in data
    assert "top_weak_knowledge_points" in data
    assert "question_type_distribution" in data
    assert "difficulty_distribution" in data
    assert "recent_daily_activity" in data
    assert "top_suggestions" in data
    # recent_daily_activity 每条有 date 和 count
    assert all("date" in d and "count" in d for d in data["recent_daily_activity"])
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -k "api" -v 2>&1 | head -15
```

Expected: `FAILED`（路由未注册，404 或 ImportError）

- [ ] **Step 3: 创建 `backend/app/api/v1/diagnosis.py`**

```python
"""学情诊断报告 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.diagnosis import DiagnosisReport
from app.services import diagnosis_service

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/report", response_model=BaseResponse[DiagnosisReport])
async def get_my_diagnosis_report(db: DbDep, current_user: UserDep):
    """返回当前学生的学情诊断报告。

    基于所有已提交错题及 AI 分析结果实时聚合，无缓存。
    """
    await get_rls_db(db, str(current_user.id))
    report = await diagnosis_service.get_diagnosis_report(
        db, student_id=current_user.id
    )
    return make_ok(report)
```

- [ ] **Step 4: 更新 `backend/app/api/v1/router.py`**

完整替换（保留现有所有 router）：

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.diagnosis import router as diagnosis_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.orders import router as orders_router
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
```

- [ ] **Step 5: 运行 API 测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_diagnosis.py -k "api" -v
```

Expected: `3 passed`

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `117 passed`（114 + 3 新增）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/diagnosis.py backend/app/api/v1/router.py \
        tests/api/test_diagnosis.py
git commit -m "feat(api): GET /diagnosis/report — learning diagnosis endpoint"
```

---

## Task 3: 集成验证 + Push + 归档 D-063

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 全部 PASS（≥117 个）

- [ ] **Step 2: 启动 live 服务器，验证新端点**

```bash
uvicorn app.main:app --port 8021 --log-level warning &
sleep 3

# 健康检查
curl -s http://localhost:8021/health | python3 -m json.tool

# /docs 正常
curl -s -o /dev/null -w "%{http_code}" http://localhost:8021/docs
echo " /docs"

# /diagnosis/report 无 token → 401
curl -s http://localhost:8021/api/v1/diagnosis/report | python3 -m json.tool

pkill -f "uvicorn app.main:app" 2>/dev/null || true
```

Expected:
- `/health` → `{"status": "ok"}`
- `/docs` → `200`
- `/diagnosis/report` 无 token → 401（`"未授权，请重新登录"`）

- [ ] **Step 3: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 4: 追加 D-063 到 `docs/决策归档.md`**

在 `## D-062` 段落之前插入：

```markdown
## D-063｜学情诊断报告：Tasks 0-3 全量交付

**日期：** 2026-05-26
**背景：** 会员支付闭环完成后，实现产品核心差异化功能——基于历史错题和 AI 分析的学情诊断报告。
**结论：**
1. **Schema（Task 0）：** `ErrorTypeCount`、`KnowledgePointCount`、`DailyActivity`、`DiagnosisReport`（含 total_questions / total_analyzed / mastered_count / mastery_rate / top_error_types / top_weak_knowledge_points / question_type_distribution / difficulty_distribution / recent_daily_activity / top_suggestions 共10个字段）。
2. **Service（Task 1）：** `get_diagnosis_report(db, *, student_id)` 直接按 student_id 查询 wrong_questions 和 ai_analyses（无需 JOIN），Python `Counter` 内存聚合；recent_daily_activity 固定返回最近30天（含0值日期，便于前端图表渲染）；top_suggestions 取最近5条不重复 AI 建议。
3. **API（Task 2）：** `GET /api/v1/diagnosis/report`，Bearer + RLS 注入，返回 `BaseResponse[DiagnosisReport]`；无数据时全零+30天空数组（不报错）。
4. **聚合策略决策：** MVP 阶段单用户 < 1000 条数据，内存聚合足够；后续如需性能优化可改为 PostgreSQL `jsonb_array_elements` unnest + GROUP BY 的纯 SQL 方案。
5. **常量：** `_TOP_N=10`（错误类型/知识点前10）、`_SUGGESTION_N=5`（建议前5）、`_ACTIVITY_DAYS=30`（活跃度天数），模块级常量便于未来调整。
**影响范围：** 全量测试 ≥117 个；1 个新端点；已推送 GitHub main 分支。

---
```

- [ ] **Step 5: 提交归档并推送**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-063 — learning diagnosis report complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | Task |
|------|------|
| 错误类型分布（前10，按频次）| Task 1 service `error_type_counter.most_common(10)` |
| 知识点薄弱项（前10，按频次）| Task 1 service `kp_counter.most_common(10)` |
| 题型分布 | Task 1 service `question_type_distribution` |
| 难度分布 | Task 1 service `difficulty_distribution` |
| 近30天每日活跃度（含0值）| Task 1 service `recent_daily_activity`，长度固定30 |
| 掌握率 | Task 1 service `mastered_count / total_questions` |
| 综合建议（最近5条）| Task 1 service `top_suggestions` |
| GET /diagnosis/report，Bearer + RLS | Task 2 endpoint |
| 无数据时返回全零（不报错）| Task 1 + Task 2 测试覆盖 |
| 401（未登录）| Task 2 测试覆盖 |

### 2. Placeholder 扫描

- 所有 Step 含完整代码 ✅
- 无 TBD / TODO ✅
- 命令含预期输出 ✅
- 测试代码具体断言（无"add appropriate assertions"）✅

### 3. 类型一致性

- `get_diagnosis_report(db, *, student_id: uuid.UUID) -> DiagnosisReport` — Task 1 service 签名与 Task 2 endpoint 调用一致 ✅
- `DiagnosisReport` 字段名在 Task 0（schema）、Task 1（service 构造）、Task 2（API 测试断言）三处完全一致 ✅
- `WrongQuestion.is_mastered`（Boolean）用于计算 `mastered_count` — 与模型定义一致（非 mastered_at）✅
- `AiAnalysis.student_id` 直接过滤，无需 JOIN — 模型确认有此字段 ✅
