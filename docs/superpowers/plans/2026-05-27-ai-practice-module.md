# AI 仿真题自主练习模块 (Module 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 AI 仿真题自主练习闭环：学生针对薄弱知识点（自动选取或手动指定）→ DeepSeek 生成单选练习题 → 学生作答 → 服务端判分并给出解析 → 查看练习历史与统计。

**Architecture:** 复用现有 `ai_questions` + `practice_records` 两表（迁移 0001 已建，**无需新迁移**）。新增 `practice_service`（生成题/判分/历史/统计）+ 4 个 API 端点挂 `/practice` 前缀。题目生成走 DeepSeek（OpenAI 兼容协议），dev 模式（`sk-placeholder` key）返回固定 mock 题。防作弊：返回学生的题目 schema 剥离 `answer`/`explanation`，提交后才揭晓。AI 返回的自由文本知识点通过 `get_or_create_knowledge_point` 映射成 `knowledge_points` 表记录以满足 FK。前端新增练习页 + 在学情报告页加"针对薄弱点练习"入口。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest-asyncio STRICT · openai SDK (DeepSeek) · uni-app Vue3

---

## File Structure

```
New backend files:
  backend/app/schemas/practice.py            # 6 schemas
  backend/app/services/practice_service.py   # 6 service functions
  backend/app/api/v1/practice.py             # 4 endpoints
  tests/api/test_practice.py                 # 18 tests

Modified backend files:
  backend/app/api/v1/router.py               # add practice_router

New frontend files:
  frontend/miniprogram/src/api/practice.ts          # 4 API call functions
  frontend/miniprogram/src/pages/practice/index.vue # 练习页：生成→作答→解析→小结

Modified frontend files:
  frontend/miniprogram/src/types/api.ts             # 6 new interfaces
  frontend/miniprogram/src/pages.json               # add 1 practice page
  frontend/miniprogram/src/pages/diagnosis/index.vue # add "针对薄弱点练习" entry button
```

**Key model facts（确认再动手）：**
- `AiQuestion`（表 `ai_questions`，迁移 0001 已建）字段：`id`, `knowledge_point_id`(FK→knowledge_points, **NOT NULL**), `unit_id`(nullable), `question_type`(enum `ai_question_type`: 单选/填空/完型/阅读/写作), `difficulty`(SmallInteger 1-5, NOT NULL), `content`(JSONB, NOT NULL), `is_active`(default true), `generated_at`(TIMESTAMPtz, **NOT NULL, 无 server_default → Python 必须显式传**), `usage_count`(default 0), `updated_at`(server_default now)
- `PracticeRecord`（表 `practice_records`）字段：`id`, `student_id`(FK→users, NOT NULL), `question_id`(FK→ai_questions, NOT NULL), `trigger_type`(enum `trigger_type`: module8_free/wrong_q_followup, NOT NULL), `student_answer`(JSONB, NOT NULL), `is_correct`(Boolean, NOT NULL), `wrong_question_id`(FK→wrong_questions, nullable), `practiced_at`(TIMESTAMPtz, **NOT NULL, 无 server_default → Python 必须显式传**), `time_spent_sec`(Integer, nullable)
- `KnowledgePoint`（表 `knowledge_points`）字段：`id`, `code`(String, **unique, NOT NULL**), `name`(String, NOT NULL), `category`(enum `knowledge_category`: grammar/vocabulary/reading/writing/listening, NOT NULL), `description`(nullable), `applicable_grades`(ARRAY[str], **NOT NULL**), `applicable_textbooks`(ARRAY[str], **NOT NULL**), `parent_id`(nullable self-FK), `sort_order`(default 0)
- `content` JSONB 约定结构（单选）：`{"stem": str, "options": [str, ...], "answer": str(正确选项的完整文本), "explanation": str}`
- 判分：`is_correct = (student_answer.strip() == content["answer"].strip())`
- `AiQuestion.content` 含 answer/explanation，**绝不可整体下发给学生**；用 `PracticeQuestionOut`（无 answer/explanation）下发，提交后用 `SubmitAnswerResult` 揭晓
- DeepSeek 配置：`settings.deepseek_api_key`（默认 `"sk-placeholder-for-dev"`）；dev 模式判定 `deepseek_api_key.startswith("sk-placeholder")`
- DeepSeek 调用（参考 `ai_service.py`）：`AsyncOpenAI(api_key=..., base_url="https://api.deepseek.com")` → `await client.chat.completions.create(model="deepseek-chat", max_tokens=..., messages=[...])` → `response.choices[0].message.content`
- 自动选薄弱知识点：复用 `diagnosis_service.get_diagnosis_report(db, student_id=...)`，取 `report.top_weak_knowledge_points[0].knowledge_point`（字符串）；列表为空则报错
- 前端 `request<T>` 已自动解包 `body.data` 并在非 200 时 reject，故 API 函数返回 `Promise<T>`（参考 `api/wrongQuestions.ts`）
- API endpoint 模式（参考 `api/v1/diagnosis.py`）：`DbDep`/`UserDep`，`await get_rls_db(db, str(current_user.id))`，写操作 `await db.commit()`，统一 `make_ok(...)` 包装
- 测试基建：`_async_session_factory`（`app.core.database`）、`upsert_user`（`app.services.auth_service`）、`@pytest.mark.asyncio`（STRICT）、`@pytest_asyncio.fixture`、`AsyncClient(transport=ASGITransport(app=app))`
- 当前全量测试数：**150**

---

## Task 0: Practice Schemas

**Files:**
- Create: `backend/app/schemas/practice.py`
- Create: `tests/api/test_practice.py`

- [ ] **Step 1: 创建测试文件并写 schema 单元测试**

用 Write 创建 `tests/api/test_practice.py`（文件不存在）：

```python
"""AI 练习模块测试。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.schemas.practice import (
    GenerateQuestionsRequest,
    PracticeQuestionOut,
    PracticeRecordOut,
    PracticeStatsOut,
    SubmitAnswerRequest,
    SubmitAnswerResult,
)


# ── Schema 单元测试 ────────────────────────────────────────────────────────────


def test_generate_request_defaults():
    req = GenerateQuestionsRequest()
    assert req.knowledge_point is None
    assert req.count == 5
    assert req.difficulty == 3


def test_generate_request_clamps_count_via_validation():
    req = GenerateQuestionsRequest(knowledge_point="一般现在时", count=3, difficulty=2)
    assert req.count == 3
    assert req.knowledge_point == "一般现在时"


def test_practice_question_out_has_no_answer_field():
    out = PracticeQuestionOut(
        id=uuid.uuid4(),
        knowledge_point_id=uuid.uuid4(),
        knowledge_point_name="一般现在时",
        question_type="单选",
        difficulty=2,
        stem="She ___ to school every day.",
        options=["go", "goes", "going", "went"],
    )
    dumped = out.model_dump()
    assert "answer" not in dumped
    assert "explanation" not in dumped
    assert dumped["options"] == ["go", "goes", "going", "went"]


def test_submit_answer_request_schema():
    req = SubmitAnswerRequest(question_id=uuid.uuid4(), answer="goes", time_spent_sec=12)
    assert req.answer == "goes"
    assert req.time_spent_sec == 12


def test_submit_answer_result_schema():
    res = SubmitAnswerResult(
        record_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        is_correct=True,
        correct_answer="goes",
        explanation="主语第三人称单数。",
    )
    assert res.is_correct is True
    assert res.correct_answer == "goes"


def test_practice_stats_out_schema():
    out = PracticeStatsOut(
        total_practiced=10,
        total_correct=7,
        correct_rate=0.7,
        by_knowledge_point={"一般现在时": {"practiced": 5, "correct": 3}},
    )
    assert out.correct_rate == 0.7
    assert out.by_knowledge_point["一般现在时"]["correct"] == 3
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_practice.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'GenerateQuestionsRequest'`

- [ ] **Step 3: 创建 `backend/app/schemas/practice.py`**

```python
"""AI 练习模块 Pydantic Schemas。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateQuestionsRequest(BaseModel):
    knowledge_point: str | None = Field(
        None, description="目标知识点；为空则自动选取学生最薄弱知识点"
    )
    count: int = Field(5, ge=1, le=10, description="生成题目数量（1-10）")
    difficulty: int = Field(3, ge=1, le=5, description="难度 1-5")


class PracticeQuestionOut(BaseModel):
    """下发给学生的题目（不含答案与解析，防作弊）。"""

    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    question_type: str
    difficulty: int
    stem: str
    options: list[str]


class SubmitAnswerRequest(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(..., min_length=1, max_length=2000)
    time_spent_sec: int | None = Field(None, ge=0)


class SubmitAnswerResult(BaseModel):
    record_id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool
    correct_answer: str
    explanation: str


class PracticeRecordOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool
    student_answer: str
    practiced_at: datetime
    time_spent_sec: int | None

    model_config = {"from_attributes": True}


class PracticeStatsOut(BaseModel):
    total_practiced: int
    total_correct: int
    correct_rate: float
    by_knowledge_point: dict[str, dict[str, int]]
```

- [ ] **Step 4: 运行 schema 测试，确认通过**

```bash
python -m pytest ../tests/api/test_practice.py -v
```

Expected: `6 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `156 passed`（150 + 6）

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/practice.py tests/api/test_practice.py
git commit -m "feat(schemas): AI practice module schemas — generate/question/submit/stats"
```

---

## Task 1: Practice Service

**Files:**
- Create: `backend/app/services/practice_service.py`
- Modify: `tests/api/test_practice.py` (append)

- [ ] **Step 1: 追加 service 集成测试到 `tests/api/test_practice.py`**

READ 文件末尾后 APPEND（不要覆盖）：

```python

# ── Service 集成测试（需要真实 DB）─────────────────────────────────────────────

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services.auth_service import upsert_user
from app.services.practice_service import (
    generate_practice_questions,
    get_or_create_knowledge_point,
    get_practice_history,
    get_practice_stats,
    get_question,
    submit_answer,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student_user(db_session):
    user = await upsert_user(db_session, openid=f"practice_svc_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


# 固定 mock：3 道单选题
_MOCK_QUESTIONS_JSON = (
    '[{"stem": "She ___ to school.", "options": ["go", "goes", "going", "gone"], '
    '"answer": "goes", "explanation": "第三人称单数。"}, '
    '{"stem": "They ___ happy.", "options": ["is", "am", "are", "be"], '
    '"answer": "are", "explanation": "复数主语用 are。"}, '
    '{"stem": "I ___ a student.", "options": ["is", "am", "are", "be"], '
    '"answer": "am", "explanation": "第一人称单数用 am。"}]'
)


def _make_mock_response(json_text: str):
    from unittest.mock import MagicMock
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = json_text
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 200
    return resp


@pytest.mark.asyncio
async def test_get_or_create_knowledge_point_creates(db_session):
    kp = await get_or_create_knowledge_point(db_session, name="一般现在时")
    await db_session.flush()
    assert kp.name == "一般现在时"
    assert kp.id is not None


@pytest.mark.asyncio
async def test_get_or_create_knowledge_point_is_idempotent(db_session):
    kp1 = await get_or_create_knowledge_point(db_session, name="时态混淆")
    await db_session.flush()
    kp2 = await get_or_create_knowledge_point(db_session, name="时态混淆")
    assert kp1.id == kp2.id


@pytest.mark.asyncio
async def test_generate_practice_questions(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=False), \
         patch("app.services.practice_service.AsyncOpenAI") as MockClient:
        from unittest.mock import MagicMock
        inst = MagicMock()
        MockClient.return_value = inst
        inst.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(_MOCK_QUESTIONS_JSON)
        )
        questions = await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point="一般现在时",
            count=3,
            difficulty=2,
        )
    await db_session.flush()
    assert len(questions) == 3
    assert questions[0].content["stem"] == "She ___ to school."
    assert questions[0].content["answer"] == "goes"
    assert questions[0].question_type == "单选"
    assert questions[0].difficulty == 2


@pytest.mark.asyncio
async def test_generate_uses_dev_mock_when_placeholder_key(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point="主谓一致",
            count=2,
            difficulty=3,
        )
    await db_session.flush()
    assert len(questions) == 2
    for q in questions:
        assert "stem" in q.content
        assert "answer" in q.content
        assert "options" in q.content


@pytest.mark.asyncio
async def test_generate_no_knowledge_point_no_diagnosis_raises(db_session, student_user):
    # 学生无错题 → 无薄弱知识点 → 报错
    with pytest.raises(AppError) as exc_info:
        await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point=None,
            count=3,
            difficulty=3,
        )
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_get_question(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="时态", count=1, difficulty=2,
        )
    await db_session.flush()
    q = await get_question(db_session, question_id=questions[0].id)
    assert q is not None
    assert q.id == questions[0].id


@pytest.mark.asyncio
async def test_submit_answer_correct(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=False), \
         patch("app.services.practice_service.AsyncOpenAI") as MockClient:
        from unittest.mock import MagicMock
        inst = MagicMock()
        MockClient.return_value = inst
        inst.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(_MOCK_QUESTIONS_JSON)
        )
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="一般现在时", count=3, difficulty=2,
        )
    await db_session.flush()
    record = await submit_answer(
        db_session,
        student_id=student_user.id,
        question_id=questions[0].id,
        answer="goes",
        time_spent_sec=10,
    )
    await db_session.flush()
    assert record.is_correct is True
    assert record.student_id == student_user.id
    assert record.trigger_type == "module8_free"


@pytest.mark.asyncio
async def test_submit_answer_wrong(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=False), \
         patch("app.services.practice_service.AsyncOpenAI") as MockClient:
        from unittest.mock import MagicMock
        inst = MagicMock()
        MockClient.return_value = inst
        inst.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(_MOCK_QUESTIONS_JSON)
        )
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="一般现在时", count=3, difficulty=2,
        )
    await db_session.flush()
    record = await submit_answer(
        db_session, student_id=student_user.id,
        question_id=questions[0].id, answer="go",
    )
    await db_session.flush()
    assert record.is_correct is False


@pytest.mark.asyncio
async def test_submit_answer_question_not_found_raises(db_session, student_user):
    with pytest.raises(AppError) as exc_info:
        await submit_answer(
            db_session, student_id=student_user.id,
            question_id=uuid.uuid4(), answer="x",
        )
    assert exc_info.value.code == 404


@pytest.mark.asyncio
async def test_get_practice_history(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="时态", count=2, difficulty=2,
        )
    await db_session.flush()
    for q in questions:
        await submit_answer(
            db_session, student_id=student_user.id,
            question_id=q.id, answer=q.content["answer"],
        )
    await db_session.flush()
    items, total = await get_practice_history(
        db_session, student_id=student_user.id, skip=0, limit=10
    )
    assert total >= 2
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_get_practice_stats(db_session, student_user):
    with patch("app.services.practice_service._is_deepseek_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="主谓一致", count=2, difficulty=2,
        )
    await db_session.flush()
    # 1 对 1 错
    await submit_answer(db_session, student_id=student_user.id,
                        question_id=questions[0].id, answer=questions[0].content["answer"])
    await submit_answer(db_session, student_id=student_user.id,
                        question_id=questions[1].id, answer="__definitely_wrong__")
    await db_session.flush()
    stats = await get_practice_stats(db_session, student_id=student_user.id)
    assert stats["total_practiced"] >= 2
    assert stats["total_correct"] >= 1
    assert 0.0 <= stats["correct_rate"] <= 1.0
```

- [ ] **Step 2: 运行，确认失败**

```bash
python -m pytest ../tests/api/test_practice.py -k "knowledge_point or generate or question or submit or history or stats" -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'get_or_create_knowledge_point'`

- [ ] **Step 3: 创建 `backend/app/services/practice_service.py`**

```python
"""AI 练习模块业务逻辑。

功能：
- get_or_create_knowledge_point: 按 name 找或建 KnowledgePoint（满足 ai_questions FK）
- generate_practice_questions: 调 DeepSeek 生成单选题，写入 ai_questions（dev mock）
- get_question: 按 id 取题（含答案，内部用）
- submit_answer: 服务端判分，写入 practice_records
- get_practice_history: 学生练习记录分页
- get_practice_stats: 练习统计（总数/正确数/正确率/按知识点）

约定：
- content JSONB = {"stem", "options": [...], "answer", "explanation"}
- 判分 is_correct = (answer.strip() == content["answer"].strip())
- dev 模式（deepseek_api_key 以 'sk-placeholder' 开头）返回固定 mock 题
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d4_knowledge import KnowledgePoint
from app.models.d6_ai_questions import AiQuestion, PracticeRecord
from app.services import diagnosis_service

_SYSTEM_PROMPT = (
    "你是专业的英语出题老师，擅长围绕指定知识点生成高质量单选练习题。"
    "请严格按 JSON 数组格式输出，不要任何额外文字或 markdown 代码块。"
)

_USER_PROMPT_TEMPLATE = """请围绕英语知识点"{knowledge_point}"，生成 {count} 道难度为 {difficulty}（1最易5最难）的单选题。

每题必须包含 4 个选项，answer 为正确选项的完整文本（与 options 中某项完全一致）。

请仅返回 JSON 数组（不要任何 markdown 代码块或额外文字）：
[
  {{
    "stem": "题干（含空格用 ___ 表示）",
    "options": ["选项A", "选项B", "选项C", "选项D"],
    "answer": "正确选项的完整文本",
    "explanation": "解析（1-2句，说明为什么）"
  }}
]"""


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _slugify_code(name: str) -> str:
    """从知识点名生成稳定唯一 code 前缀（非 ASCII 用 hex 兜底）。"""
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    if not ascii_part:
        ascii_part = "kp"
    return ascii_part[:40]


async def get_or_create_knowledge_point(
    db: AsyncSession,
    *,
    name: str,
    category: str = "grammar",
) -> KnowledgePoint:
    """按 name 查找知识点；不存在则创建（默认 category=grammar）。"""
    result = await db.execute(select(KnowledgePoint).where(KnowledgePoint.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    code = f"auto_{_slugify_code(name)}_{uuid.uuid4().hex[:8]}"
    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=code,
        name=name,
        category=category,  # type: ignore[arg-type]
        description=None,
        applicable_grades=[],
        applicable_textbooks=[],
        sort_order=0,
    )
    db.add(kp)
    await db.flush()
    return kp


def _dev_mock_questions(knowledge_point: str, count: int) -> list[dict]:
    """dev 模式返回固定 mock 题（围绕知识点变体）。"""
    base = [
        {
            "stem": f"[{knowledge_point}] She ___ to school every day.",
            "options": ["go", "goes", "going", "gone"],
            "answer": "goes",
            "explanation": "主语 She 第三人称单数，动词用 goes。",
        },
        {
            "stem": f"[{knowledge_point}] They ___ very happy today.",
            "options": ["is", "am", "are", "be"],
            "answer": "are",
            "explanation": "复数主语 They 用 are。",
        },
        {
            "stem": f"[{knowledge_point}] I ___ a middle school student.",
            "options": ["is", "am", "are", "be"],
            "answer": "am",
            "explanation": "第一人称单数 I 用 am。",
        },
    ]
    out: list[dict] = []
    for i in range(count):
        out.append(base[i % len(base)])
    return out


async def generate_practice_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    knowledge_point: str | None,
    count: int,
    difficulty: int,
) -> list[AiQuestion]:
    """生成并落库练习题。

    - knowledge_point 为空 → 取学生最薄弱知识点（无则 AppError 400）
    - dev 模式 → 固定 mock；否则调 DeepSeek
    - DeepSeek 错误 → AppError(502)；JSON 解析失败 → AppError(500)
    """
    # 1. 解析目标知识点
    kp_name = knowledge_point
    if not kp_name:
        report = await diagnosis_service.get_diagnosis_report(db, student_id=student_id)
        if not report.top_weak_knowledge_points:
            raise AppError(code=400, message="暂无薄弱知识点，请先上传错题并完成 AI 分析")
        kp_name = report.top_weak_knowledge_points[0].knowledge_point

    kp = await get_or_create_knowledge_point(db, name=kp_name)

    # 2. 取题目数据（mock 或 DeepSeek）
    if _is_deepseek_dev_mode():
        raw_questions = _dev_mock_questions(kp_name, count)
    else:
        prompt = _USER_PROMPT_TEMPLATE.format(
            knowledge_point=kp_name, count=count, difficulty=difficulty
        )
        try:
            client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com",
            )
            response = await client.chat.completions.create(
                model="deepseek-chat",
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(code=502, message=f"AI出题服务暂时不可用，请稍后重试（{exc}）") from exc

        raw_text = (response.choices[0].message.content or "").strip()
        # 去掉可能的 markdown 代码块包裹
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw_text).strip()
        try:
            raw_questions = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AppError(code=500, message="AI出题返回格式异常") from exc
        if not isinstance(raw_questions, list) or not raw_questions:
            raise AppError(code=500, message="AI出题返回内容为空")

    # 3. 落库
    now = datetime.now(timezone.utc)
    created: list[AiQuestion] = []
    for rq in raw_questions[:count]:
        if not all(k in rq for k in ("stem", "options", "answer", "explanation")):
            continue
        q = AiQuestion(
            id=uuid.uuid4(),
            knowledge_point_id=kp.id,
            unit_id=None,
            question_type="单选",  # type: ignore[arg-type]
            difficulty=difficulty,
            content={
                "stem": rq["stem"],
                "options": rq["options"],
                "answer": rq["answer"],
                "explanation": rq["explanation"],
            },
            is_active=True,
            generated_at=now,
            usage_count=0,
        )
        db.add(q)
        created.append(q)

    if not created:
        raise AppError(code=500, message="AI出题返回内容无有效题目")

    await db.flush()
    return created


async def get_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
) -> AiQuestion | None:
    """按 id 取题（含答案，内部判分/下发用）。"""
    result = await db.execute(select(AiQuestion).where(AiQuestion.id == question_id))
    return result.scalar_one_or_none()


async def submit_answer(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    question_id: uuid.UUID,
    answer: str,
    time_spent_sec: int | None = None,
) -> PracticeRecord:
    """服务端判分并写入 practice_records。题不存在 → AppError(404)。"""
    question = await get_question(db, question_id=question_id)
    if question is None:
        raise AppError(code=404, message="题目不存在")

    correct_answer = str(question.content.get("answer", "")).strip()
    is_correct = answer.strip() == correct_answer

    record = PracticeRecord(
        id=uuid.uuid4(),
        student_id=student_id,
        question_id=question_id,
        trigger_type="module8_free",  # type: ignore[arg-type]
        student_answer={"answer": answer},
        is_correct=is_correct,
        wrong_question_id=None,
        practiced_at=datetime.now(timezone.utc),
        time_spent_sec=time_spent_sec,
    )
    db.add(record)
    question.usage_count = (question.usage_count or 0) + 1
    await db.flush()
    return record


async def get_practice_history(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[PracticeRecord], int]:
    """分页返回学生练习记录（按时间倒序）+ 总数。"""
    count_result = await db.execute(
        select(func.count())
        .select_from(PracticeRecord)
        .where(PracticeRecord.student_id == student_id)
    )
    total = int(count_result.scalar_one())

    result = await db.execute(
        select(PracticeRecord)
        .where(PracticeRecord.student_id == student_id)
        .order_by(PracticeRecord.practiced_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def get_practice_stats(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> dict:
    """聚合练习统计：总数、正确数、正确率、按知识点细分。"""
    # JOIN ai_questions → knowledge_points 获取知识点名
    result = await db.execute(
        select(
            PracticeRecord.is_correct,
            KnowledgePoint.name,
        )
        .join(AiQuestion, AiQuestion.id == PracticeRecord.question_id)
        .join(KnowledgePoint, KnowledgePoint.id == AiQuestion.knowledge_point_id)
        .where(PracticeRecord.student_id == student_id)
    )
    rows = result.all()

    total_practiced = len(rows)
    total_correct = sum(1 for r in rows if r.is_correct)
    correct_rate = round(total_correct / total_practiced, 4) if total_practiced > 0 else 0.0

    by_kp: dict[str, dict[str, int]] = defaultdict(lambda: {"practiced": 0, "correct": 0})
    for r in rows:
        by_kp[r.name]["practiced"] += 1
        if r.is_correct:
            by_kp[r.name]["correct"] += 1

    return {
        "total_practiced": total_practiced,
        "total_correct": total_correct,
        "correct_rate": correct_rate,
        "by_knowledge_point": dict(by_kp),
    }
```

- [ ] **Step 4: 运行 service 测试，确认通过**

```bash
python -m pytest ../tests/api/test_practice.py -k "knowledge_point or generate or question or submit or history or stats" -v
```

Expected: `11 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `167 passed`（156 + 11）

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/practice_service.py tests/api/test_practice.py
git commit -m "feat(service): AI practice service — generate/submit/history/stats + dev mock"
```

---

## Task 2: Practice API Endpoints + Router

**Files:**
- Create: `backend/app/api/v1/practice.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_practice.py` (append)

- [ ] **Step 1: 追加 API 集成测试到 `tests/api/test_practice.py`**

READ 文件末尾后 APPEND：

```python

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
        mock_wx.return_value = {"openid": f"practice_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_generate_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 3, "difficulty": 2},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_questions_api(client: AsyncClient, auth_headers):
    """dev 模式下（默认 placeholder key）直接生成 mock 题。"""
    resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 3, "difficulty": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    questions = body["data"]
    assert len(questions) == 3
    # 防作弊：下发题目不含 answer / explanation
    assert "answer" not in questions[0]
    assert "explanation" not in questions[0]
    assert "options" in questions[0]
    assert questions[0]["knowledge_point_name"] == "一般现在时"


@pytest.mark.asyncio
async def test_submit_answer_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 1, "difficulty": 2},
        headers=auth_headers,
    )
    q = gen_resp.json()["data"][0]
    # dev mock 第一题 answer 是 "goes"
    submit_resp = await client.post(
        "/api/v1/practice/submit",
        json={"question_id": q["id"], "answer": "goes", "time_spent_sec": 8},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 200, submit_resp.text
    data = submit_resp.json()["data"]
    assert data["is_correct"] is True
    assert data["correct_answer"] == "goes"
    assert "explanation" in data


@pytest.mark.asyncio
async def test_submit_answer_not_found_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/practice/submit",
        json={"question_id": str(uuid.uuid4()), "answer": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_practice_history_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "时态", "count": 2, "difficulty": 2},
        headers=auth_headers,
    )
    for q in gen_resp.json()["data"]:
        await client.post(
            "/api/v1/practice/submit",
            json={"question_id": q["id"], "answer": "goes"},
            headers=auth_headers,
        )
    resp = await client.get("/api/v1/practice/history", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] >= 2
    assert isinstance(body["data"]["items"], list)


@pytest.mark.asyncio
async def test_practice_stats_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "主谓一致", "count": 2, "difficulty": 2},
        headers=auth_headers,
    )
    questions = gen_resp.json()["data"]
    await client.post(
        "/api/v1/practice/submit",
        json={"question_id": questions[0]["id"], "answer": "goes"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/practice/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_practiced" in data
    assert "correct_rate" in data
    assert "by_knowledge_point" in data
```

- [ ] **Step 2: 运行，确认失败**

```bash
python -m pytest ../tests/api/test_practice.py -k "api or requires_auth" -v 2>&1 | head -10
```

Expected: `404`（路由未注册）

- [ ] **Step 3: 创建 `backend/app/api/v1/practice.py`**

```python
"""AI 练习模块 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d4_knowledge import KnowledgePoint
from app.schemas.base import BaseResponse, make_ok
from app.schemas.practice import (
    GenerateQuestionsRequest,
    PracticeQuestionOut,
    PracticeRecordOut,
    PracticeStatsOut,
    SubmitAnswerRequest,
    SubmitAnswerResult,
)
from app.services import practice_service
from sqlalchemy import select

router = APIRouter(prefix="/practice", tags=["practice"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/generate", response_model=BaseResponse[list[PracticeQuestionOut]])
async def generate_questions(
    body: GenerateQuestionsRequest,
    db: DbDep,
    current_user: UserDep,
):
    """生成练习题（不下发答案/解析）。knowledge_point 为空则自动选最薄弱知识点。"""
    await get_rls_db(db, str(current_user.id))
    questions = await practice_service.generate_practice_questions(
        db,
        student_id=current_user.id,
        knowledge_point=body.knowledge_point,
        count=body.count,
        difficulty=body.difficulty,
    )
    await db.commit()

    # 查知识点名（所有题同一知识点）
    kp_id = questions[0].knowledge_point_id
    kp_result = await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))
    kp = kp_result.scalar_one()

    return make_ok(
        [
            PracticeQuestionOut(
                id=q.id,
                knowledge_point_id=q.knowledge_point_id,
                knowledge_point_name=kp.name,
                question_type=str(q.question_type),
                difficulty=q.difficulty,
                stem=q.content["stem"],
                options=q.content["options"],
            )
            for q in questions
        ]
    )


@router.post("/submit", response_model=BaseResponse[SubmitAnswerResult])
async def submit_answer(
    body: SubmitAnswerRequest,
    db: DbDep,
    current_user: UserDep,
):
    """提交答案，服务端判分并返回正确答案与解析。"""
    await get_rls_db(db, str(current_user.id))
    record = await practice_service.submit_answer(
        db,
        student_id=current_user.id,
        question_id=body.question_id,
        answer=body.answer,
        time_spent_sec=body.time_spent_sec,
    )
    question = await practice_service.get_question(db, question_id=body.question_id)
    await db.commit()

    return make_ok(
        SubmitAnswerResult(
            record_id=record.id,
            question_id=body.question_id,
            is_correct=record.is_correct,
            correct_answer=str(question.content.get("answer", "")),
            explanation=str(question.content.get("explanation", "")),
        )
    )


@router.get("/history", response_model=BaseResponse[dict])
async def practice_history(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """分页返回练习历史。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await practice_service.get_practice_history(
        db, student_id=current_user.id, skip=skip, limit=limit
    )
    return make_ok(
        {
            "total": total,
            "items": [
                PracticeRecordOut(
                    id=r.id,
                    question_id=r.question_id,
                    is_correct=r.is_correct,
                    student_answer=str(r.student_answer.get("answer", "")),
                    practiced_at=r.practiced_at,
                    time_spent_sec=r.time_spent_sec,
                ).model_dump(mode="json")
                for r in items
            ],
        }
    )


@router.get("/stats", response_model=BaseResponse[PracticeStatsOut])
async def practice_stats(db: DbDep, current_user: UserDep):
    """返回练习统计。"""
    await get_rls_db(db, str(current_user.id))
    stats = await practice_service.get_practice_stats(db, student_id=current_user.id)
    return make_ok(PracticeStatsOut(**stats))
```

- [ ] **Step 4: 更新 `backend/app/api/v1/router.py`**

用 Edit 添加 import 与 include。将：
```python
from app.api.v1.ocr import router as ocr_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.wrong_questions import router as wrong_questions_router
```
改为：
```python
from app.api.v1.ocr import router as ocr_router
from app.api.v1.practice import router as practice_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.wrong_questions import router as wrong_questions_router
```

将末尾：
```python
v1_router.include_router(ocr_router)
v1_router.include_router(teacher_router)
```
改为：
```python
v1_router.include_router(ocr_router)
v1_router.include_router(teacher_router)
v1_router.include_router(practice_router)
```

- [ ] **Step 5: 运行 API 测试，确认通过**

```bash
python -m pytest ../tests/api/test_practice.py -k "api or requires_auth" -v
```

Expected: `6 passed`

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `173 passed`（167 + 6）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/practice.py backend/app/api/v1/router.py tests/api/test_practice.py
git commit -m "feat(api): practice endpoints — generate/submit/history/stats"
```

---

## Task 3: Frontend — Practice Page + Types + Diagnosis Entry

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/practice.ts`
- Modify: `frontend/miniprogram/src/pages.json`
- Create: `frontend/miniprogram/src/pages/practice/index.vue`
- Modify: `frontend/miniprogram/src/pages/diagnosis/index.vue`

- [ ] **Step 1: 追加类型到 `frontend/miniprogram/src/types/api.ts`**

READ 文件末尾后 APPEND：

```typescript

// ── Practice (AI 仿真题) ──────────────────────────────────────────────────────

export interface GenerateQuestionsRequest {
  knowledge_point?: string | null
  count?: number
  difficulty?: number
}

export interface PracticeQuestionOut {
  id: string
  knowledge_point_id: string
  knowledge_point_name: string
  question_type: string
  difficulty: number
  stem: string
  options: string[]
}

export interface SubmitAnswerRequest {
  question_id: string
  answer: string
  time_spent_sec?: number | null
}

export interface SubmitAnswerResult {
  record_id: string
  question_id: string
  is_correct: boolean
  correct_answer: string
  explanation: string
}

export interface PracticeRecordOut {
  id: string
  question_id: string
  is_correct: boolean
  student_answer: string
  practiced_at: string
  time_spent_sec: number | null
}

export interface PracticeHistoryOut {
  total: number
  items: PracticeRecordOut[]
}

export interface PracticeStatsOut {
  total_practiced: number
  total_correct: number
  correct_rate: number
  by_knowledge_point: Record<string, { practiced: number; correct: number }>
}
```

- [ ] **Step 2: 创建 `frontend/miniprogram/src/api/practice.ts`**

```typescript
import { request } from '@/utils/request'
import type {
  PracticeQuestionOut,
  SubmitAnswerResult,
  PracticeHistoryOut,
  PracticeStatsOut,
} from '@/types/api'

export function generateQuestions(
  knowledgePoint: string | null,
  count = 5,
  difficulty = 3,
): Promise<PracticeQuestionOut[]> {
  return request<PracticeQuestionOut[]>('/api/v1/practice/generate', {
    method: 'POST',
    data: { knowledge_point: knowledgePoint, count, difficulty },
  })
}

export function submitAnswer(
  questionId: string,
  answer: string,
  timeSpentSec?: number,
): Promise<SubmitAnswerResult> {
  return request<SubmitAnswerResult>('/api/v1/practice/submit', {
    method: 'POST',
    data: { question_id: questionId, answer, time_spent_sec: timeSpentSec ?? null },
  })
}

export function getPracticeHistory(skip = 0, limit = 20): Promise<PracticeHistoryOut> {
  return request<PracticeHistoryOut>(`/api/v1/practice/history?skip=${skip}&limit=${limit}`)
}

export function getPracticeStats(): Promise<PracticeStatsOut> {
  return request<PracticeStatsOut>('/api/v1/practice/stats')
}
```

- [ ] **Step 3: 更新 `pages.json`（添加练习页）**

READ `frontend/miniprogram/src/pages.json`，在 `pages` 数组末尾（`pages/profile/index` 之后）追加一项。用 Edit 将：
```json
    {
      "path": "pages/profile/index",
      "style": { "navigationBarTitleText": "我的" }
    }
  ],
```
改为：
```json
    {
      "path": "pages/profile/index",
      "style": { "navigationBarTitleText": "我的" }
    },
    {
      "path": "pages/practice/index",
      "style": { "navigationBarTitleText": "AI 练习" }
    }
  ],
```

> 注意：若 `pages.json` 中 profile 项后面已有 teacher 页（如教师模块已添加），则改为在数组最后一个对象后插入 practice 项，保持 JSON 合法（逗号正确）。READ 当前内容后定位真实的数组末尾再编辑。

- [ ] **Step 4: 创建目录与 `pages/practice/index.vue`**

```bash
mkdir -p /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/frontend/miniprogram/src/pages/practice
```

创建 `frontend/miniprogram/src/pages/practice/index.vue`：

```vue
<!-- src/pages/practice/index.vue -->
<template>
  <view class="practice-page">

    <!-- 开始界面 -->
    <view v-if="phase === 'start'" class="card">
      <view class="card-title">AI 仿真题练习</view>
      <text class="hint">针对你的薄弱知识点生成练习题。留空则自动选取最薄弱知识点。</text>
      <input
        v-model="kpInput"
        class="input"
        placeholder="目标知识点（选填，如：一般现在时）"
      />
      <view class="row">
        <text class="row-label">题量</text>
        <view class="seg">
          <text
            v-for="n in [3, 5, 8]"
            :key="n"
            class="seg-item"
            :class="{ active: count === n }"
            @tap="count = n"
          >{{ n }}</text>
        </view>
      </view>
      <view class="row">
        <text class="row-label">难度</text>
        <view class="seg">
          <text
            v-for="d in [1, 2, 3, 4, 5]"
            :key="d"
            class="seg-item"
            :class="{ active: difficulty === d }"
            @tap="difficulty = d"
          >{{ d }}</text>
        </view>
      </view>
      <button class="btn-primary" :disabled="loading" @tap="startPractice">
        {{ loading ? '出题中（约3-8秒）…' : '开始练习' }}
      </button>
    </view>

    <!-- 答题界面 -->
    <view v-else-if="phase === 'doing'" class="card">
      <view class="progress">第 {{ currentIndex + 1 }} / {{ questions.length }} 题 · {{ current.knowledge_point_name }}</view>
      <view class="stem">{{ current.stem }}</view>
      <view
        v-for="opt in current.options"
        :key="opt"
        class="option"
        :class="optionClass(opt)"
        @tap="selectOption(opt)"
      >{{ opt }}</view>

      <view v-if="result" class="result-box" :class="result.is_correct ? 'ok' : 'bad'">
        <text class="result-title">{{ result.is_correct ? '✅ 回答正确' : '❌ 回答错误' }}</text>
        <text v-if="!result.is_correct" class="result-answer">正确答案：{{ result.correct_answer }}</text>
        <text class="result-explain">{{ result.explanation }}</text>
      </view>

      <button
        v-if="!result"
        class="btn-primary"
        :disabled="!selected || submitting"
        @tap="submitCurrent"
      >{{ submitting ? '提交中…' : '提交答案' }}</button>
      <button v-else class="btn-primary" @tap="nextQuestion">
        {{ currentIndex + 1 < questions.length ? '下一题' : '查看小结' }}
      </button>
    </view>

    <!-- 小结界面 -->
    <view v-else class="card">
      <view class="card-title">练习小结</view>
      <view class="summary-score">{{ correctCount }} / {{ questions.length }}</view>
      <text class="summary-rate">正确率 {{ Math.round((correctCount / questions.length) * 100) }}%</text>
      <button class="btn-primary" @tap="restart">再练一组</button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { generateQuestions, submitAnswer } from '@/api/practice'
import type { PracticeQuestionOut, SubmitAnswerResult } from '@/types/api'

type Phase = 'start' | 'doing' | 'summary'

const phase = ref<Phase>('start')
const kpInput = ref('')
const count = ref(5)
const difficulty = ref(3)
const loading = ref(false)

const questions = ref<PracticeQuestionOut[]>([])
const currentIndex = ref(0)
const selected = ref('')
const submitting = ref(false)
const result = ref<SubmitAnswerResult | null>(null)
const correctCount = ref(0)
let questionStart = 0

const current = computed(() => questions.value[currentIndex.value])

async function startPractice() {
  loading.value = true
  try {
    const data = await generateQuestions(kpInput.value || null, count.value, difficulty.value)
    if (data.length === 0) {
      uni.showToast({ title: '未生成题目，请重试', icon: 'none' })
      return
    }
    questions.value = data
    currentIndex.value = 0
    correctCount.value = 0
    result.value = null
    selected.value = ''
    questionStart = Date.now()
    phase.value = 'doing'
  } catch (e: any) {
    uni.showToast({ title: e?.message || '出题失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function selectOption(opt: string) {
  if (result.value) return // 已提交不可改
  selected.value = opt
}

function optionClass(opt: string) {
  if (!result.value) return { selected: selected.value === opt }
  // 已提交：高亮正确答案与错选
  if (opt === result.value.correct_answer) return { correct: true }
  if (opt === selected.value) return { wrong: true }
  return {}
}

async function submitCurrent() {
  if (!selected.value) return
  submitting.value = true
  try {
    const timeSpent = Math.round((Date.now() - questionStart) / 1000)
    const res = await submitAnswer(current.value.id, selected.value, timeSpent)
    result.value = res
    if (res.is_correct) correctCount.value++
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function nextQuestion() {
  if (currentIndex.value + 1 < questions.value.length) {
    currentIndex.value++
    selected.value = ''
    result.value = null
    questionStart = Date.now()
  } else {
    phase.value = 'summary'
  }
}

function restart() {
  phase.value = 'start'
}
</script>

<style scoped>
.practice-page { padding: 16rpx; background: #f5f5f5; min-height: 100vh; }
.card { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 16rpx; }
.card-title { font-size: 30rpx; font-weight: 600; color: #222; margin-bottom: 16rpx; }
.hint { font-size: 24rpx; color: #888; display: block; margin-bottom: 16rpx; line-height: 1.5; }
.input { border: 1rpx solid #e8e8e8; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.row { display: flex; align-items: center; margin-bottom: 16rpx; }
.row-label { width: 80rpx; font-size: 26rpx; color: #666; }
.seg { display: flex; gap: 12rpx; flex: 1; }
.seg-item { flex: 1; text-align: center; padding: 12rpx 0; border: 1rpx solid #e0e0e0; border-radius: 8rpx; font-size: 26rpx; color: #555; }
.seg-item.active { border-color: #1677ff; color: #1677ff; background: #f0f7ff; }
.btn-primary { background: #1677ff; color: #fff; border-radius: 8rpx; padding: 20rpx; font-size: 28rpx; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { opacity: 0.5; }
.progress { font-size: 24rpx; color: #888; margin-bottom: 16rpx; }
.stem { font-size: 30rpx; color: #222; line-height: 1.6; margin-bottom: 20rpx; }
.option { border: 1rpx solid #e8e8e8; border-radius: 8rpx; padding: 18rpx 20rpx; font-size: 28rpx; color: #333; margin-bottom: 12rpx; }
.option.selected { border-color: #1677ff; background: #f0f7ff; }
.option.correct { border-color: #52c41a; background: #f6ffed; color: #389e0d; }
.option.wrong { border-color: #ff4d4f; background: #fff1f0; color: #cf1322; }
.result-box { border-radius: 8rpx; padding: 16rpx; margin: 16rpx 0; display: flex; flex-direction: column; gap: 6rpx; }
.result-box.ok { background: #f6ffed; }
.result-box.bad { background: #fff1f0; }
.result-title { font-size: 28rpx; font-weight: 600; }
.result-answer { font-size: 26rpx; color: #cf1322; }
.result-explain { font-size: 26rpx; color: #555; line-height: 1.5; }
.summary-score { font-size: 64rpx; font-weight: 700; color: #1677ff; text-align: center; margin: 24rpx 0 8rpx; }
.summary-rate { font-size: 28rpx; color: #888; text-align: center; display: block; margin-bottom: 24rpx; }
</style>
```

- [ ] **Step 5: 在 `diagnosis/index.vue` 添加练习入口**

READ `frontend/miniprogram/src/pages/diagnosis/index.vue` 完整内容，定位模板根 `</view>` 闭合前（`</template>` 之前）的位置，用 Edit 插入入口卡片：

```vue
    <!-- 针对薄弱点练习入口 -->
    <view class="card practice-entry">
      <view class="card-title">智能练习</view>
      <text class="practice-desc">基于你的薄弱知识点，AI 实时生成针对性练习题。</text>
      <button class="btn-practice" @tap="goPractice">开始 AI 练习</button>
    </view>
```

在 `<script setup>` 中追加（若已有 `import` 区，放在合适位置）：
```typescript
function goPractice() {
  uni.navigateTo({ url: '/pages/practice/index' })
}
```

在 `<style scoped>` 末尾（`</style>` 前）追加：
```css
.practice-entry { margin-top: 16rpx; }
.practice-desc { font-size: 24rpx; color: #888; display: block; margin-bottom: 12rpx; line-height: 1.5; }
.btn-practice { background: #1677ff; color: #fff; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; text-align: center; }
```

**具体操作**：READ `diagnosis/index.vue` 全文确认现有模板结构（卡片 class 名、根 view 的 class），定位 `</template>` 前最后一个根级 `</view>`，在其前插入上述卡片；script 中函数区追加 `goPractice`；style 末尾追加 CSS。若该页 class 命名与 `.card`/`.card-title` 不同，沿用该页已有的卡片 class 命名，仅新增 `.practice-entry`/`.practice-desc`/`.btn-practice`。

- [ ] **Step 6: 提交前端**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/practice.ts \
        frontend/miniprogram/src/pages.json \
        frontend/miniprogram/src/pages/practice/ \
        frontend/miniprogram/src/pages/diagnosis/index.vue
git commit -m "feat(frontend): AI practice page — generate/answer/summary + diagnosis entry"
```

---

## Task 4: Integration + Push + 归档 D-070

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -12
```

Expected: 全部 PASS（≥ 173）

- [ ] **Step 2: 验证 live server**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
uvicorn app.main:app --port 8023 --log-level warning &
sleep 3

curl -s http://localhost:8023/health

curl -s http://localhost:8023/openapi.json | python3 -c "
import json,sys
spec = json.load(sys.stdin)
paths = list(spec['paths'].keys())
practice_paths = [p for p in paths if '/practice' in p]
print('Practice paths:', practice_paths)
print('Count:', len(practice_paths))
"

# 未登录访问 → 401
curl -s -X POST http://localhost:8023/api/v1/practice/generate \
  -H "Content-Type: application/json" \
  -d '{"knowledge_point":"时态","count":3,"difficulty":2}' | python3 -m json.tool

pkill -f "uvicorn app.main:app --port 8023" 2>/dev/null || true
```

Expected:
- `{"status": "ok"}`
- Practice paths 含 4 条（`/practice/generate`, `/practice/submit`, `/practice/history`, `/practice/stats`）
- 未登录 generate → 401

- [ ] **Step 3: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 4: 追加 D-070 到 `docs/决策归档.md`**

READ `docs/决策归档.md` 顶部，找到当前最新条目（D-069，教师模块）的 `## D-069` 标题，用 Edit 在其**前面**插入（逆序排列，新决策在最上）：

```markdown
## D-070｜AI 仿真题自主练习模块 (Module 8)

**日期：** 2026-05-27
**背景：** 学情诊断报告已能定位学生薄弱知识点，但缺少"诊断→练习→提升"闭环的练习环节。本模块让学生针对薄弱点（自动选取或手动指定）由 AI 即时生成练习题并作答、判分、看解析。
**结论：**
1. **复用既有表，无新迁移：** 直接使用迁移 0001 已建的 `ai_questions` + `practice_records` 两表。
2. **知识点 FK 处理：** `ai_questions.knowledge_point_id` 为 NOT NULL FK，而 AI 诊断的知识点是自由文本字符串；新增 `get_or_create_knowledge_point(name)` 按名查找或自动创建 KnowledgePoint（生成唯一 code，默认 category=grammar，applicable_grades/textbooks 置空数组）以满足 FK。
3. **防作弊设计：** 生成题目下发用 `PracticeQuestionOut`（仅 stem + options，**剥离 answer/explanation**）；学生 `POST /practice/submit` 后由服务端判分（`answer.strip() == content["answer"].strip()`）并用 `SubmitAnswerResult` 揭晓正确答案与解析。
4. **自动选薄弱点：** `generate` 未传 knowledge_point 时，复用 `diagnosis_service.get_diagnosis_report` 取 `top_weak_knowledge_points[0]`；无数据则返回 400 提示先上传错题。
5. **Dev mock：** `deepseek_api_key` 以 `sk-placeholder` 开头时返回固定 mock 单选题，整条链路无需真实 API key 即可测试。
6. **API：** 4 个端点 `/practice/generate`(POST)、`/practice/submit`(POST)、`/practice/history`(GET)、`/practice/stats`(GET)。
7. **前端：** `pages/practice/index.vue`（开始→答题→即时解析→小结三阶段），学情报告页追加"开始 AI 练习"入口。
8. **测试：** 23 个测试全部通过（6 schema + 11 service + 6 API 集成）。
**影响范围：** 0 新迁移；4 个新 API 端点；1 个新前端页；已推送 GitHub main 分支。

---

```

- [ ] **Step 5: 提交归档并推送**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-070 — AI practice module (Module 8) complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | Task |
|------|------|
| 针对薄弱知识点生成练习题 | Task 1 `generate_practice_questions` + Task 2 `POST /practice/generate` |
| 自动选取最薄弱知识点 | Task 1（复用 diagnosis_service）|
| 手动指定知识点 | Task 0 `GenerateQuestionsRequest.knowledge_point` |
| 知识点 FK 映射 | Task 1 `get_or_create_knowledge_point` |
| 防作弊（不下发答案）| Task 0 `PracticeQuestionOut`（无 answer/explanation）+ Task 2 generate endpoint |
| 服务端判分 | Task 1 `submit_answer` + Task 2 `POST /practice/submit` |
| 揭晓答案与解析 | Task 0 `SubmitAnswerResult` + Task 2 submit endpoint |
| 练习历史 | Task 1 `get_practice_history` + Task 2 `GET /practice/history` |
| 练习统计 | Task 1 `get_practice_stats` + Task 2 `GET /practice/stats` |
| Dev mock | Task 1 `_dev_mock_questions` + `_is_deepseek_dev_mode` |
| 前端练习页 | Task 3 `pages/practice/index.vue` |
| 学情报告入口 | Task 3 diagnosis/index.vue 修改 |
| 全量测试 ≥ 173 | Task 4 验证 |

### 2. Placeholder 扫描

- 所有 service/API/schema 函数含完整代码 ✅
- 前端 Step 5（diagnosis 入口）需 READ 后定位插入点，已给出具体指令与降级说明 ✅
- 无 TBD / TODO ✅

### 3. 类型一致性

- `generate_practice_questions(db, *, student_id, knowledge_point, count, difficulty) -> list[AiQuestion]` — Task 1 定义，Task 2 endpoint 调用 ✅
- `submit_answer(db, *, student_id, question_id, answer, time_spent_sec=None) -> PracticeRecord` — Task 1，Task 2 ✅
- `get_practice_history(...) -> tuple[list[PracticeRecord], int]` — Task 1 返回 (items, total)，Task 2 解包为 {total, items} ✅
- `get_practice_stats(...) -> dict`（含 total_practiced/total_correct/correct_rate/by_knowledge_point）— Task 1，Task 2 `PracticeStatsOut(**stats)` ✅
- `PracticeQuestionOut` 字段（id/knowledge_point_id/knowledge_point_name/question_type/difficulty/stem/options）后端 schema 与前端 interface 一致 ✅
- `SubmitAnswerResult` 字段（record_id/question_id/is_correct/correct_answer/explanation）前后端一致 ✅
- content JSONB key（stem/options/answer/explanation）在 service 生成、判分、endpoint 下发处一致引用 ✅
- dev mock 第一题 answer="goes" — Task 2 `test_submit_answer_api` 据此断言 ✅
