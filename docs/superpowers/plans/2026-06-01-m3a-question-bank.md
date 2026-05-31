# M3a: V2 仿真题库 + 逐题练习流 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 为知识点生成仿真题（单选/填空/判断 3 类，每 KP 5 题），用户在 KP 详情页点"练习"进入逐题作答流（即时反馈+解析），做错的题自动写入 wrong_questions 走 V1 错题分析链路。

**Architecture:** 复用已有 `simulated_questions`（d12）+ `wrong_questions`（d3）表，扩 `ai_question_type` enum 加 "判断"。新增 1 个 AI 生题 service（仿 curriculum_ai_service 模式）+ 1 个 question service（CRUD + 答题逻辑 + 错题落库）+ 1 个 API 路由 + 1 个 seed 脚本 + 1 个前端"练习"页。沿用 M2 的 dev mock + paywall + design token 模式。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Alembic 0009 + AsyncOpenAI (DeepSeek) + uni-app Vue3 + Pinia + pytest-asyncio

---

## 文件结构

### 后端新增

| 文件 | 责任 |
|---|---|
| `backend/alembic/versions/0009_add_judge_question_type.py` | 加 "判断" 到 ai_question_type enum |
| `backend/app/schemas/questions.py` | AIGeneratedQuestion / SimQuestionOut / PracticeAttemptIn / PracticeResultOut |
| `backend/app/services/question_ai_service.py` | DeepSeek 生题（5 题/KP），dev mock 返回固定结构 |
| `backend/app/services/question_service.py` | persist_questions / list_questions_by_kp / submit_practice_attempt（含错题落库） |
| `backend/app/api/v1/questions.py` | GET /kp/{id}/practice-questions / POST /practice-attempts |
| `backend/scripts/seed_questions.py` | CLI: 遍历 KP 调 AI + persist，断点续传 |
| `tests/services/test_question_ai_service.py` | dev mock 输出结构 |
| `tests/services/test_question_service.py` | persist 幂等 + 答题判分 + 错题落库 |
| `tests/api/test_questions.py` | 3 端点集成测试 |

### 后端修改

| 文件 | 改动 |
|---|---|
| `backend/app/models/d6_ai_questions.py` | enum 加 "判断"（与迁移同步） |
| `backend/app/api/v1/router.py` | 注册 questions_router |

### 前端新增

| 文件 | 责任 |
|---|---|
| `frontend/miniprogram/src/api/questions.ts` | listPracticeQuestions / submitAttempt |
| `frontend/miniprogram/src/pages/practice/v2-session.vue` | 逐题练习页（题干 + 选项/输入 + 即时反馈 + 下一题） |

### 前端修改

| 文件 | 改动 |
|---|---|
| `frontend/miniprogram/src/types/api.ts` | 加 SimQuestionOut / PracticeAttemptIn / PracticeResultOut |
| `frontend/miniprogram/src/pages.json` | 注册 pages/practice/v2-session |
| `frontend/miniprogram/src/pages/curriculum/kp-content.vue` | 页底加"开始练习"按钮 → 跳 v2-session |

---

## 数据流概览

```
seed_questions.py --kp <UUID> --count 5
  ↓ for each KP
question_ai_service.generate_questions(kp, count=5)
  ↓ AsyncOpenAI(deepseek-chat) → JSON list[AIGeneratedQuestion]
question_service.persist_questions()
  ↓ insert SimulatedQuestion rows (status=published, generated_by=ai_full)

前端练习
  GET /kp/{kp_id}/practice-questions?limit=5
    → SimQuestionOut[]（受 paywall 约束：所属 unit_no=1 永免；其余按 PurchasedSemester）
  用户作答某题
  POST /practice-attempts { question_id, user_answer }
    → 后端判分（单选/判断严格匹配；填空 case-insensitive trim 后任意一个候选答案命中）
    → 错误时自动写 wrong_questions 行（user_id + sim_question_id + answers + auto-link KP）
    → 返回 PracticeResultOut { correct: bool, correct_answer, explanation }
```

---

## 题型三件套定义

| 题型 enum 值 | options JSONB | answer 字段 | 判分逻辑 |
|---|---|---|---|
| `单选` | `["A. ...", "B. ...", "C. ...", "D. ..."]`（4 个字符串） | `"A"` / `"B"` / `"C"` / `"D"` | strict equal |
| `填空` | `null` | `"goes"` 或多候选 `"goes\|go"`（`\|` 分隔多个合法答案） | trim().lower() 后任一候选命中 |
| `判断` | `null` | `"对"` / `"错"`（或 `T`/`F`） | strict equal |

---

## Task 0: Alembic 0009 — Enum 加 "判断"

**Files:**
- Create: `backend/alembic/versions/0009_add_judge_question_type.py`
- Modify: `backend/app/models/d6_ai_questions.py:15-18` (enum 定义同步)

- [ ] **Step 1: 查最新 revision id**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && alembic current 2>&1 | tail -2`
Expected: 输出当前版本号（应为 0008 之类）

- [ ] **Step 2: 创建迁移文件**

Create `backend/alembic/versions/0009_add_judge_question_type.py`:

```python
"""add 判断 to ai_question_type enum

Revision ID: 0009_add_judge
Revises: 0008_v2_extensions_and_pricing_seed
Create Date: 2026-06-01

"""
from alembic import op

revision = "0009_add_judge"
down_revision = "0008_v2_extensions_and_pricing_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: ALTER TYPE ... ADD VALUE 必须在 transaction 外
    op.execute("COMMIT")
    op.execute("ALTER TYPE ai_question_type ADD VALUE IF NOT EXISTS '判断'")


def downgrade() -> None:
    # PG 不支持从 enum 删值（除非重建类型）；M3a 不做回滚
    pass
```

> 注意：如果当前 `alembic current` 不是 `0008_v2_extensions_and_pricing_seed`，把 `down_revision` 改成实际的最新版本字符串。

- [ ] **Step 3: 跑迁移**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && alembic upgrade head 2>&1 | tail -5`
Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> 0009_add_judge`

- [ ] **Step 4: 验证 enum 含 "判断"**

Run:
```bash
docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "SELECT enum_range(NULL::ai_question_type);"
```
Expected: 包含 `判断` 的列表

- [ ] **Step 5: 模型 enum 同步**

Edit `backend/app/models/d6_ai_questions.py` 行 15-18：

```python
ai_question_type_enum = sa.Enum(
    "单选", "填空", "完型", "阅读", "写作", "判断",
    name="ai_question_type",
)
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0009_add_judge_question_type.py backend/app/models/d6_ai_questions.py && git commit -m "$(cat <<'EOF'
feat(m3): alembic 0009 — add 判断 to ai_question_type enum

M3a needs 判断 as 3rd question type alongside existing 单选/填空. PG
enum value adds require COMMIT before ALTER TYPE; downgrade not
supported (PG doesn't allow enum value removal without type rebuild).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/questions.py`

- [ ] **Step 1: 创建 schemas/questions.py**

```python
"""V2 仿真题 + 练习 Pydantic schemas（D-079 / M3a）。"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


# ─── AI 生成输出（question_ai_service → question_service.persist）─

class AIGeneratedQuestion(BaseModel):
    question_type: Literal["单选", "填空", "判断"]
    stem: str = Field(..., min_length=5, description="题干文本")
    options: list[str] | None = Field(
        None, description="单选题为 4 个选项字符串；填空/判断为 null"
    )
    answer: str = Field(..., min_length=1, description="单选: A-D；填空: 答案 或 多候选用 | 分隔；判断: 对/错")
    explanation: str = Field(..., min_length=10, description="解析")
    difficulty: int = Field(..., ge=1, le=5)


# ─── API 响应/请求 ─────────────────────────────────────────────────────────

class SimQuestionOut(BaseModel):
    """前端拿到的题目（不带 answer 防作弊）。"""
    id: uuid.UUID
    question_type: str
    stem: str
    options: list[str] | None = None
    difficulty: int


class PracticeAttemptIn(BaseModel):
    question_id: uuid.UUID
    user_answer: str = Field(..., min_length=1, max_length=500)


class PracticeResultOut(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str
    wrong_question_id: uuid.UUID | None = Field(
        None, description="做错时自动落 wrong_questions 表，返回 id 方便前端跳错题详情"
    )
```

- [ ] **Step 2: 验证 import**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python -c "from app.schemas.questions import AIGeneratedQuestion, SimQuestionOut, PracticeAttemptIn, PracticeResultOut; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/questions.py && git commit -m "feat(m3): add questions pydantic schemas"
```

---

## Task 2: AI 生题 Service（含 dev mock）

**Files:**
- Create: `backend/app/services/question_ai_service.py`
- Create: `tests/services/test_question_ai_service.py`

- [ ] **Step 1: 写失败测试**

Create `tests/services/test_question_ai_service.py`:

```python
"""question_ai_service dev mock 测试。"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.question_ai_service import generate_questions


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest.mark.asyncio
async def test_mock_returns_3_question_types():
    """dev mock 必须包含 3 种题型（单选/填空/判断），每种至少 1 道。"""
    qs = await generate_questions(
        kp_name="There be 句型",
        kp_category="grammar",
        kp_description="表示存在",
        count=5,
    )
    assert len(qs) == 5
    types = {q.question_type for q in qs}
    assert types == {"单选", "填空", "判断"}

    for q in qs:
        if q.question_type == "单选":
            assert q.options is not None
            assert len(q.options) == 4
            assert q.answer in ["A", "B", "C", "D"]
        elif q.question_type == "填空":
            assert q.options is None
            assert q.answer  # 非空字符串
        elif q.question_type == "判断":
            assert q.options is None
            assert q.answer in ["对", "错"]
        assert q.explanation  # 非空
        assert 1 <= q.difficulty <= 5


@pytest.mark.asyncio
async def test_mock_deterministic_per_kp_name():
    """同名 KP 多次调用应该至少 type 分布一致（便于幂等 upsert）。"""
    q1 = await generate_questions(kp_name="X", kp_category="grammar", kp_description="d", count=5)
    q2 = await generate_questions(kp_name="X", kp_category="grammar", kp_description="d", count=5)
    assert sorted([q.question_type for q in q1]) == sorted([q.question_type for q in q2])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_question_ai_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 question_ai_service.py**

Create `backend/app/services/question_ai_service.py`:

```python
"""V2 仿真题 AI 生成 service（D-079 / M3a）。

调 DeepSeek 为某个知识点生成 N 道题（单选/填空/判断 3 类混合）。
dev mode 返回固定结构供前端/集成测试无 key 时跑通。
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.questions import AIGeneratedQuestion

_SYSTEM_PROMPT = (
    "你是中国中小学英语命题老师，按知识点出仿真题。题型在单选/填空/判断三类中分配。"
    "严格按 JSON 数组输出，不要任何 markdown 代码块或额外文字。"
)

_USER_PROMPT_TEMPLATE = """请为以下知识点生成 {count} 道仿真题。

知识点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

题型分配（{count} 道）：
- 单选 ≥ 2 道：4 个选项，标记 A-D，answer 是单个字母
- 填空 ≥ 1 道：options 为 null，answer 可用 | 分隔多个合法答案（如 "goes|go"）
- 判断 ≥ 1 道：options 为 null，answer 是 "对" 或 "错"

每题必须含 explanation（≥ 20 字解析）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{
    "question_type": "单选",
    "stem": "题干...",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "B",
    "explanation": "...",
    "difficulty": 2
  }},
  {{
    "question_type": "填空",
    "stem": "He ___ to school every day.",
    "options": null,
    "answer": "goes",
    "explanation": "...",
    "difficulty": 2
  }},
  {{
    "question_type": "判断",
    "stem": "There be 句型只能用于现在时。",
    "options": null,
    "answer": "错",
    "explanation": "...",
    "difficulty": 1
  }}
]"""


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _make_mock_questions(kp_name: str, count: int) -> list[AIGeneratedQuestion]:
    """dev mock：固定 5 题（2 单选 + 2 填空 + 1 判断）。"""
    base = [
        AIGeneratedQuestion(
            question_type="单选",
            stem=f"Mock 单选题 1 about {kp_name}.",
            options=["A. mock1", "B. mock2", "C. mock3", "D. mock4"],
            answer="B",
            explanation="Mock 解析：答案是 B 因为...",
            difficulty=2,
        ),
        AIGeneratedQuestion(
            question_type="单选",
            stem=f"Mock 单选题 2 about {kp_name}.",
            options=["A. opt1", "B. opt2", "C. opt3", "D. opt4"],
            answer="A",
            explanation="Mock 解析：选 A 是因为...",
            difficulty=3,
        ),
        AIGeneratedQuestion(
            question_type="填空",
            stem=f"Mock 填空题 1 about {kp_name}: He ___ play.",
            options=None,
            answer="can|may",
            explanation="Mock 解析：can 和 may 都接受。",
            difficulty=2,
        ),
        AIGeneratedQuestion(
            question_type="填空",
            stem=f"Mock 填空题 2 about {kp_name}: She ___ home.",
            options=None,
            answer="went",
            explanation="Mock 解析：went 是 go 的过去式。",
            difficulty=3,
        ),
        AIGeneratedQuestion(
            question_type="判断",
            stem=f"Mock 判断题 about {kp_name}: This rule applies always.",
            options=None,
            answer="错",
            explanation="Mock 解析：并非总是适用。",
            difficulty=1,
        ),
    ]
    # 如果 count != 5，循环取
    return [base[i % len(base)] for i in range(count)]


async def generate_questions(
    *,
    kp_name: str,
    kp_category: str,
    kp_description: str | None,
    count: int = 5,
) -> list[AIGeneratedQuestion]:
    """为 1 个 KP 生成 count 道仿真题。"""
    if _is_deepseek_dev_mode():
        return _make_mock_questions(kp_name, count)

    prompt = _USER_PROMPT_TEMPLATE.format(
        count=count,
        kp_name=kp_name,
        kp_category=kp_category,
        kp_description=kp_description or "(无)",
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI 生题失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    # 剥 markdown 围栏
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="AI 生题返回格式异常")

    try:
        return [AIGeneratedQuestion(**item) for item in data]
    except Exception as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_question_ai_service.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/question_ai_service.py tests/services/test_question_ai_service.py && git commit -m "feat(m3): add question_ai_service with dev mock (3 types)"
```

---

## Task 3: question_service（persist + 答题 + 错题落库）

**Files:**
- Create: `backend/app/services/question_service.py`
- Create: `tests/services/test_question_service.py`

- [ ] **Step 1: 写失败测试**

Create `tests/services/test_question_service.py`:

```python
"""question_service 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.services import question_ai_service, question_service
from app.services.auth_service import upsert_user


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def seeded_kp(db_session):
    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=f"test-kp-{uuid.uuid4().hex[:6]}",
        name="测试 KP",
        category="grammar",
        description="测试用",
        applicable_grades=["小学5年级"],
        applicable_textbooks=["译林版"],
    )
    db_session.add(kp)
    await db_session.flush()
    return kp


@pytest.mark.asyncio
async def test_persist_questions_creates_5_rows(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    assert len(created) == 5

    rows = (await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all()
    assert len(rows) >= 5  # >= 因为可能有其他 KP 测试残留


@pytest.mark.asyncio
async def test_persist_idempotent(db_session, seeded_kp):
    """同 KP 跑两次：应保留第一次的数据，第二次不再加（按 stem 判重）。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()

    cnt1 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())

    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()

    cnt2 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())

    assert cnt1 == cnt2


@pytest.mark.asyncio
async def test_grading_单选_strict_equal(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem="X", options=["A", "B", "C", "D"],
        answer="B", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()

    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    # 答对
    r1 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="B",
    )
    assert r1.correct is True
    assert r1.wrong_question_id is None

    # 答错
    r2 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="A",
    )
    assert r2.correct is False
    assert r2.correct_answer == "B"
    assert r2.wrong_question_id is not None


@pytest.mark.asyncio
async def test_grading_填空_case_insensitive_multi_answer(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="填空", stem="X", options=None,
        answer="goes|go", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()

    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    # 两个候选都对
    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="goes")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="GO ")
    assert r2.correct is True  # case-insensitive + trim

    # 错的
    r3 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="went")
    assert r3.correct is False


@pytest.mark.asyncio
async def test_grading_判断_strict(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="判断", stem="X", options=None,
        answer="错", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()

    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="错")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="对")
    assert r2.correct is False


@pytest.mark.asyncio
async def test_wrong_attempt_creates_wrong_question_with_kp_link(db_session, seeded_kp):
    """错题应自动写 wrong_questions + wrong_question_knowledge_points。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem="判断题干", options=["A.x", "B.y", "C.z", "D.w"],
        answer="A", explanation="解析", difficulty=2, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="D",
    )
    assert r.wrong_question_id is not None

    wq = (await db_session.execute(
        select(WrongQuestion).where(WrongQuestion.id == r.wrong_question_id)
    )).scalar_one()
    assert wq.student_id == user.id
    assert "判断题干" in (wq.question_text or "")
    assert wq.student_answer == "D"
    assert wq.correct_answer == "A"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_question_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 question_service.py**

> 实现前先 Read `backend/app/models/d3_wrong_questions.py` 确认 `WrongQuestion` 字段（student_id / question_text / student_answer / correct_answer / question_type / source_type / ...）以及 `WrongQuestionKnowledgePoint` 链接结构。

Create `backend/app/services/question_service.py`:

```python
"""V2 仿真题 service（D-079 / M3a）。

职责：
1. persist_questions() — AI 生成 → SimulatedQuestion 行（按 stem 幂等去重）
2. list_questions_by_kp() — 给 API 用的读取（不带 answer，前端拿不到答案）
3. submit_attempt() — 判分 + 错题落库 + 返回结果
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import WrongQuestionKnowledgePoint, KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.schemas.questions import (
    AIGeneratedQuestion, PracticeResultOut, SimQuestionOut,
)


# ─── Persist ────────────────────────────────────────────────────────────────

async def persist_questions(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    questions: list[AIGeneratedQuestion],
) -> list[SimulatedQuestion]:
    """按 (kp_id, stem) 幂等 upsert 仿真题。返回本次确保入库的所有行。"""
    out: list[SimulatedQuestion] = []
    for q in questions:
        existing = (await db.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp_id,
                SimulatedQuestion.stem == q.stem,
            )
        )).scalar_one_or_none()
        if existing is not None:
            # 已存在，跳过；返回旧行以便调用方知道总集
            out.append(existing)
            continue
        sq = SimulatedQuestion(
            id=uuid.uuid4(),
            knowledge_point_id=kp_id,
            question_type=q.question_type,
            stem=q.stem,
            options=q.options,
            answer=q.answer,
            explanation=q.explanation,
            difficulty=q.difficulty,
            status="published",
        )
        db.add(sq)
        await db.flush()
        out.append(sq)
    return out


# ─── Read ───────────────────────────────────────────────────────────────────

async def list_questions_by_kp(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    limit: int = 5,
) -> list[SimQuestionOut]:
    rows = (await db.execute(
        select(SimulatedQuestion)
        .where(
            SimulatedQuestion.knowledge_point_id == kp_id,
            SimulatedQuestion.status == "published",
        )
        .order_by(SimulatedQuestion.created_at)
        .limit(limit)
    )).scalars().all()
    return [SimQuestionOut(
        id=r.id,
        question_type=str(r.question_type),
        stem=r.stem,
        options=r.options,
        difficulty=r.difficulty,
    ) for r in rows]


# ─── Grading ────────────────────────────────────────────────────────────────

def _grade(question_type: str, correct_answer: str, user_answer: str) -> bool:
    ua = user_answer.strip()
    ca = correct_answer.strip()
    if question_type == "单选":
        return ua.upper() == ca.upper()
    if question_type == "判断":
        return ua == ca
    if question_type == "填空":
        # answer 字段可能是 "goes|go|went" 多候选
        candidates = [c.strip().lower() for c in ca.split("|") if c.strip()]
        return ua.lower() in candidates
    return ua == ca  # 兜底


async def submit_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    user_answer: str,
) -> PracticeResultOut:
    q = (await db.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")

    correct = _grade(str(q.question_type), q.answer, user_answer)

    wq_id: uuid.UUID | None = None
    if not correct:
        # 写 wrong_questions 行 + 自动关联 KP
        wq = WrongQuestion(
            id=uuid.uuid4(),
            student_id=user_id,
            question_text=q.stem,
            student_answer=user_answer,
            correct_answer=q.answer,
            question_type=str(q.question_type),
            source_type="practice",  # 表示来自 V2 练习
        )
        db.add(wq)
        await db.flush()
        # 关联 KP
        db.add(WrongQuestionKnowledgePoint(
            wrong_question_id=wq.id,
            knowledge_point_id=q.knowledge_point_id,
        ))
        await db.flush()
        wq_id = wq.id

    return PracticeResultOut(
        correct=correct,
        correct_answer=q.answer,
        explanation=q.explanation or "",
        wrong_question_id=wq_id,
    )
```

- [ ] **Step 4: 运行测试确认 6 通过**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_question_service.py -v`
Expected: 6 PASSED

> 若 `WrongQuestion` 字段名与实现假设不一致（例如 `source_type` 不存在），按 d3_wrong_questions.py 实际定义调整代码。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/question_service.py tests/services/test_question_service.py && git commit -m "feat(m3): add question_service (persist + grading + wrong-q logging)"
```

---

## Task 4: API Endpoints

**Files:**
- Create: `backend/app/api/v1/questions.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `tests/api/test_questions.py`

- [ ] **Step 1: 写失败集成测试**

Create `tests/api/test_questions.py`:

```python
"""V2 questions API 集成测试（D-079 / M3a）。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.main import app
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.services import question_ai_service, question_service


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"m3_q_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_kp_with_questions() -> tuple[uuid.UUID, uuid.UUID]:
    """返回 (kp_id, single_choice_question_id)；新 session 提交，跨请求可见。"""
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(),
            code=f"m3-test-{uuid.uuid4().hex[:8]}",
            name="M3 测试 KP",
            category="grammar",
            description="m3 test",
            applicable_grades=["小学5年级"],
            applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        qs = await question_ai_service.generate_questions(
            kp_name=kp.name, kp_category="grammar", kp_description="d", count=5,
        )
        await question_service.persist_questions(s, kp_id=kp.id, questions=qs)
        await s.commit()

        # 取第一道单选题的 id
        first_single = (await s.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp.id,
                SimulatedQuestion.question_type == "单选",
            ).limit(1)
        )).scalar_one()
        return kp.id, first_single.id


@pytest.mark.asyncio
async def test_list_questions_returns_no_answers(client):
    """前端拿到的题目不能含 answer 字段（防作弊）。"""
    kp_id, _ = await _seed_kp_with_questions()
    h = await _login(client, f"l_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions?limit=5",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) >= 5
    for q in items:
        assert "answer" not in q  # 不暴露
        assert q["stem"]
        assert q["question_type"] in ["单选", "填空", "判断"]


@pytest.mark.asyncio
async def test_submit_correct_attempt(client):
    """单选题答对：correct=true, 无 wrong_question_id。"""
    _, q_id = await _seed_kp_with_questions()
    # mock 单选答案是 B（dev mock 固定）
    h = await _login(client, f"c_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/questions/practice-attempts",
        json={"question_id": str(q_id), "user_answer": "B"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["correct"] is True
    assert body["wrong_question_id"] is None
    assert body["correct_answer"] == "B"
    assert body["explanation"]


@pytest.mark.asyncio
async def test_submit_wrong_attempt_creates_wrong_q(client):
    """单选题答错：correct=false, 返回 wrong_question_id。"""
    _, q_id = await _seed_kp_with_questions()
    h = await _login(client, f"w_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/questions/practice-attempts",
        json={"question_id": str(q_id), "user_answer": "D"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["correct"] is False
    assert body["wrong_question_id"] is not None
    assert body["correct_answer"] == "B"
```

- [ ] **Step 2: 运行确认 fail（404）**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/api/test_questions.py -v`
Expected: 3 FAIL with 404

- [ ] **Step 3: 创建 API 路由 `backend/app/api/v1/questions.py`**

> 先 Read `backend/app/api/v1/curriculum.py` 确认 import 路径（应是 `from app.core.database import get_db` + `from app.core.security import get_current_user` + `from app.schemas.base import make_ok`）。

```python
"""V2 仿真题 + 练习 API（D-079 / M3a）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.questions import PracticeAttemptIn
from app.services import question_service

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/kp/{kp_id}/practice-questions")
async def list_practice_questions(
    kp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
):
    items = await question_service.list_questions_by_kp(db, kp_id=kp_id, limit=limit)
    return make_ok([i.model_dump(mode="json") for i in items])


@router.post("/practice-attempts")
async def submit_practice_attempt(
    body: PracticeAttemptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await question_service.submit_attempt(
        db,
        user_id=current_user.id,
        question_id=body.question_id,
        user_answer=body.user_answer,
    )
    await db.commit()  # 错题落库要 commit
    return make_ok(result.model_dump(mode="json"))
```

- [ ] **Step 4: 注册路由**

Edit `backend/app/api/v1/router.py` 加 import + include：
```python
from app.api.v1.questions import router as questions_router
# ...
v1_router.include_router(questions_router)
```

- [ ] **Step 5: 跑测试确认 3 PASS**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/api/test_questions.py -v`
Expected: 3 PASSED

- [ ] **Step 6: 跑全套确认无回归**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest -q 2>&1 | tail -3`
Expected: 全绿（previous 247 + 11 新 = 258）

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/questions.py backend/app/api/v1/router.py tests/api/test_questions.py && git commit -m "feat(m3): add questions API (list practice + submit attempt)"
```

---

## Task 5: Seed CLI（先只跑 8 个 free-unit KP）

**Files:**
- Create: `backend/scripts/seed_questions.py`

- [ ] **Step 1: 创建 seed 脚本**

```python
"""V2 仿真题批量 seed 脚本（D-079 / M3a）。

用法：
  # 跑指定 KP id 的题目（5 题）
  python backend/scripts/seed_questions.py --kp <uuid>

  # 跑某单元下所有 KP（默认每 KP 5 题）
  python backend/scripts/seed_questions.py --unit <uuid>

  # 跑某 (textbook, grade, semester, unit_no) 单元
  python backend/scripts/seed_questions.py --textbook 译林版 --grade 小学5年级 --semester 上 --unit-no 1

  # 跑全部 free-unit（每学期 unit_no=1）的 KP
  python backend/scripts/seed_questions.py --all-free

幂等：按 (kp_id, stem) 去重，重跑只增量。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d4_knowledge import (  # noqa: E402
    CurriculumUnit, KnowledgePoint, UnitKnowledgePoint,
)
from app.services import question_ai_service, question_service  # noqa: E402


async def seed_one_kp(kp_id, count: int = 5) -> int:
    """为 1 个 KP 生成 count 道题；返回新增数。"""
    async with _async_session_factory() as db:
        kp = (await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )).scalar_one_or_none()
        if kp is None:
            print(f"  [skip] KP {kp_id} 不存在")
            return 0

        print(f"  [gen]  {kp.name} ({str(kp.category)}) ...", end=" ", flush=True)
        qs = await question_ai_service.generate_questions(
            kp_name=kp.name,
            kp_category=str(kp.category),
            kp_description=kp.description,
            count=count,
        )
        rows = await question_service.persist_questions(db, kp_id=kp.id, questions=qs)
        await db.commit()
        print(f"✓ {len(rows)} 道（含已存在）")
        return len(rows)


async def list_kps_for_unit(
    textbook: str, grade: str, semester: str, unit_no: int,
) -> list:
    async with _async_session_factory() as db:
        rows = (await db.execute(
            select(KnowledgePoint).join(
                UnitKnowledgePoint,
                UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
            ).join(
                CurriculumUnit, CurriculumUnit.id == UnitKnowledgePoint.unit_id,
            ).where(
                CurriculumUnit.textbook_version == textbook,
                CurriculumUnit.grade == grade,
                CurriculumUnit.semester == semester,
                CurriculumUnit.unit_no == unit_no,
            )
        )).scalars().all()
        return list(rows)


FREE_UNITS = [
    ("译林版", "小学5年级", "上", 1),
    ("译林版", "小学5年级", "下", 1),
    ("译林版", "初中7年级", "上", 1),
    ("译林版", "初中7年级", "下", 1),
]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kp", help="KP UUID")
    p.add_argument("--textbook", default="译林版")
    p.add_argument("--grade")
    p.add_argument("--semester")
    p.add_argument("--unit-no", type=int)
    p.add_argument("--count", type=int, default=5, help="每 KP 题数")
    p.add_argument("--all-free", action="store_true", help="跑全部 free-unit KP")
    args = p.parse_args()

    if args.kp:
        import uuid as _u
        await seed_one_kp(_u.UUID(args.kp), args.count)
        return

    targets: list[tuple] = []
    if args.all_free:
        targets = FREE_UNITS
    elif args.grade and args.semester and args.unit_no:
        targets = [(args.textbook, args.grade, args.semester, args.unit_no)]
    else:
        p.error("必须提供 --kp / --all-free / 或 (--grade --semester --unit-no)")

    for textbook, grade, semester, unit_no in targets:
        print(f"\n=== {textbook} {grade} {semester} U{unit_no} ===")
        kps = await list_kps_for_unit(textbook, grade, semester, unit_no)
        if not kps:
            print(f"  (无 KP，跳过；先跑 M2 seed_curriculum 灌单元内容)")
            continue
        for kp in kps:
            await seed_one_kp(kp.id, args.count)
    print("\n✓ 完成")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: dev mock 跑 1 个 KP（任挑 1 个）**

Run:
```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && \
KP_ID=$(docker exec enggramer-pg-dev psql -U postgres -d enggramer -t -c "SELECT id FROM knowledge_points WHERE code LIKE 'yl-g5s1-u1-%' LIMIT 1;" | xargs) && \
PYTHONPATH=. python scripts/seed_questions.py --kp "$KP_ID"
```
Expected: `[gen]  ... ✓ 5 道`

- [ ] **Step 3: 跑全部 free-unit（dev mock 下 < 1 分钟）**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && PYTHONPATH=. python scripts/seed_questions.py --all-free 2>&1 | tail -20`
Expected: 4 个学期段；只有 `小学5年级 上 U1` 有 KP（8 个 KP），其余学期/单元的 KP 是 mock 文本可能没 link，会显示 "无 KP" 或仅 1 个 KP（dev mock 每单元生成 3 KP，但只有 U1 真 AI 有 8 个）

- [ ] **Step 4: 数据库验证**

Run: `docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "SELECT count(*) AS sim_q FROM simulated_questions WHERE status='published';"`
Expected: count ≥ 40（8 KP × 5 题）

- [ ] **Step 5: Commit**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && git add backend/scripts/seed_questions.py && git commit -m "feat(m3): add seed_questions CLI (--kp / --all-free / by unit)"
```

---

## Task 6: 前端 API + 类型

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/questions.ts`

- [ ] **Step 1: 加类型到 types/api.ts 末尾**

```typescript
// ─── V2 仿真题（D-079 / M3a）──
export interface SimQuestionOut {
  id: string
  question_type: '单选' | '填空' | '判断'
  stem: string
  options: string[] | null
  difficulty: number
}

export interface PracticeAttemptIn {
  question_id: string
  user_answer: string
}

export interface PracticeResultOut {
  correct: boolean
  correct_answer: string
  explanation: string
  wrong_question_id: string | null
}
```

- [ ] **Step 2: 创建 api/questions.ts**

```typescript
import { request } from '@/utils/request'
import type { SimQuestionOut, PracticeAttemptIn, PracticeResultOut } from '@/types/api'

export function listPracticeQuestions(kpId: string, limit = 5): Promise<SimQuestionOut[]> {
  return request<SimQuestionOut[]>(
    `/api/v1/questions/kp/${kpId}/practice-questions`,
    { method: 'GET', data: { limit } },
  )
}

export function submitAttempt(body: PracticeAttemptIn): Promise<PracticeResultOut> {
  return request<PracticeResultOut>('/api/v1/questions/practice-attempts', {
    method: 'POST',
    data: body,
  })
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/src/api/questions.ts frontend/miniprogram/src/types/api.ts && git commit -m "feat(m3): add questions frontend API + types"
```

---

## Task 7: 练习页 + KP 入口接入 + pages.json

**Files:**
- Create: `frontend/miniprogram/src/pages/practice/v2-session.vue`
- Modify: `frontend/miniprogram/src/pages.json`
- Modify: `frontend/miniprogram/src/pages/curriculum/kp-content.vue`

- [ ] **Step 1: 创建练习页 v2-session.vue**

```vue
<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!questions.length" class="empty">该知识点暂无题目</view>

    <view v-else-if="!finished">
      <view class="progress">
        <text>{{ currentIdx + 1 }} / {{ questions.length }}</text>
      </view>

      <view class="card">
        <view class="qtype">{{ current.question_type }} · 难度 {{ current.difficulty }}</view>
        <text class="stem">{{ current.stem }}</text>

        <!-- 单选 -->
        <view v-if="current.question_type === '单选' && current.options" class="options">
          <view
            v-for="(opt, i) in current.options" :key="i"
            class="option"
            :class="{
              selected: userAnswer === letter(i),
              correct: feedback && letter(i) === feedback.correct_answer,
              wrong: feedback && userAnswer === letter(i) && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = letter(i))"
          >{{ opt }}</view>
        </view>

        <!-- 填空 -->
        <view v-else-if="current.question_type === '填空'" class="fill">
          <input
            v-model="userAnswer"
            class="fill-input"
            placeholder="请输入答案"
            :disabled="!!feedback"
          />
        </view>

        <!-- 判断 -->
        <view v-else-if="current.question_type === '判断'" class="judge">
          <view
            v-for="opt in ['对', '错']" :key="opt"
            class="option"
            :class="{
              selected: userAnswer === opt,
              correct: feedback && opt === feedback.correct_answer,
              wrong: feedback && userAnswer === opt && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = opt)"
          >{{ opt }}</view>
        </view>

        <!-- 反馈 -->
        <view v-if="feedback" class="feedback" :class="{ ok: feedback.correct }">
          <text class="fb-title">{{ feedback.correct ? '✓ 答对了' : '✗ 答错了' }}</text>
          <text class="fb-ans">正确答案：{{ feedback.correct_answer }}</text>
          <text class="fb-exp">{{ feedback.explanation }}</text>
        </view>

        <button
          class="btn-primary"
          :disabled="!canSubmit"
          @tap="feedback ? next() : submit()"
        >
          {{ feedback ? (isLast ? '完成' : '下一题') : '提交答案' }}
        </button>
      </view>
    </view>

    <view v-else class="finish-card card">
      <text class="finish-title">练习完成</text>
      <text class="finish-meta">共 {{ questions.length }} 题，对 {{ correctCount }} 道</text>
      <button class="btn-primary" @tap="goBack">返回</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listPracticeQuestions, submitAttempt } from '@/api/questions'
import type { SimQuestionOut, PracticeResultOut } from '@/types/api'

const kpId = ref('')
const questions = ref<SimQuestionOut[]>([])
const currentIdx = ref(0)
const userAnswer = ref('')
const feedback = ref<PracticeResultOut | null>(null)
const correctCount = ref(0)
const loading = ref(true)
const finished = ref(false)

const current = computed(() => questions.value[currentIdx.value])
const isLast = computed(() => currentIdx.value === questions.value.length - 1)
const canSubmit = computed(() => !!feedback.value || (userAnswer.value && userAnswer.value.trim()))

function letter(i: number): string {
  return ['A', 'B', 'C', 'D'][i] || ''
}

onLoad(async (q: any) => {
  kpId.value = q.kp || ''
  if (!kpId.value) {
    uni.showToast({ title: '缺少 kp 参数', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  try {
    questions.value = await listPracticeQuestions(kpId.value, 5)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function submit() {
  if (!current.value) return
  try {
    const r = await submitAttempt({
      question_id: current.value.id,
      user_answer: userAnswer.value.trim(),
    })
    feedback.value = r
    if (r.correct) correctCount.value++
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  }
}

function next() {
  if (isLast.value) {
    finished.value = true
    return
  }
  currentIdx.value++
  userAnswer.value = ''
  feedback.value = null
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.progress { text-align: center; padding: 16rpx 0; font-size: 24rpx; color: var(--c-text-second); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 600; color: var(--c-ink); line-height: 1.5; margin-bottom: 24rpx; }
.options, .judge { display: flex; flex-direction: column; gap: 12rpx; margin-bottom: 24rpx; }
.option { padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-gold); background: var(--c-primary-faint); font-weight: 600; }
.option.correct { border-color: #2ecc71; background: #eafaf1; }
.option.wrong { border-color: var(--c-danger); background: var(--c-danger-bg); }
.fill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 20rpx; font-size: 28rpx; margin-bottom: 24rpx; box-sizing: border-box; width: 100%; }
.feedback { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 8rpx; }
.feedback.ok { background: #eafaf1; }
.fb-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.fb-ans { font-size: 24rpx; color: var(--c-text-body); }
.fb-exp { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.finish-card { display: flex; flex-direction: column; gap: 16rpx; align-items: center; text-align: center; padding: 48rpx; }
.finish-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.finish-meta { font-size: 28rpx; color: var(--c-text-second); }
</style>
```

- [ ] **Step 2: pages.json 注册**

Insert into the `pages` array:

```json
{ "path": "pages/practice/v2-session", "style": { "navigationBarTitleText": "练习" } },
```

- [ ] **Step 3: kp-content.vue 加"开始练习"按钮**

打开 `frontend/miniprogram/src/pages/curriculum/kp-content.vue`，在 `</scroll-view>` 之后、`</template>` 之前插入：

```vue
    <view class="practice-bar">
      <button class="btn-primary" @tap="goPractice">开始练习（5 题）</button>
    </view>
```

在 `<script setup>` 加：

```typescript
function goPractice() {
  // q.id from onLoad scope is the kp id
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}` })
}
```

并把 `onLoad` 改成保存 kpId：

```typescript
const kpId = ref('')
onLoad(async (q: any) => {
  kpId.value = q.id || ''
  try {
    contents.value = await getKpContents(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})
```

CSS 加：

```css
.practice-bar { padding: 24rpx; background: var(--c-bg-card); border-top: 1rpx solid var(--c-border); }
```

> 注意：实施前先 Read 当前 kp-content.vue 内容，确认 `kpId` 是否已存在变量、避免重复定义。

- [ ] **Step 4: 验证 pages.json 仍 valid + Commit**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/frontend/miniprogram && python3 -c "import json; json.load(open('src/pages.json'))" && cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && git add frontend/miniprogram/src/pages/practice/v2-session.vue frontend/miniprogram/src/pages/curriculum/kp-content.vue frontend/miniprogram/src/pages.json && git commit -m "$(cat <<'EOF'
feat(m3): add V2 practice session page + KP entry button

Task 7 of M3a. v2-session.vue is the per-question feedback flow:
fetches 5 questions for the KP, shows one at a time, supports
单选/填空/判断 input modes, calls submitAttempt on submit, displays
correct/wrong + answer + explanation inline, advances to next, ends
with a summary card.

kp-content page footer gets "开始练习（5 题）" button → routes to
the session with kpId.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 真 AI 跑 free-unit + 真机验证 + D-082 归档

- [ ] **Step 1: 真实 AI 重生（清掉 dev mock 题目，跑真 AI）**

```bash
docker exec -i enggramer-pg-dev psql -U postgres -d enggramer <<'EOF'
DELETE FROM simulated_questions
  WHERE knowledge_point_id IN (
    SELECT id FROM knowledge_points WHERE code LIKE 'yl-g5s1-u1-%'
  );
EOF
```

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && \
time PYTHONPATH=. python scripts/seed_questions.py --grade 小学5年级 --semester 上 --unit-no 1 2>&1 | tail -15
```

Expected: 8 KP × 5 题 = 40 题，~3-5 分钟（每 KP 一次 AI 调用），cost ~$0.1

- [ ] **Step 2: 质量人工抽检**

```bash
docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "
SELECT sq.question_type, substring(sq.stem, 1, 50) AS stem_preview, sq.answer, sq.difficulty
FROM simulated_questions sq
JOIN knowledge_points kp ON kp.id = sq.knowledge_point_id
WHERE kp.code = 'yl-g5s1-u1-kp1'
ORDER BY sq.created_at;
"
```

人工核查：题目是否符合 KP 主题、3 种题型分布合理、answer 字段格式正确（单选 A-D、判断 对/错、填空合理）。

- [ ] **Step 3: 重启 uvicorn + 前端 build 确保更新**

```bash
lsof -i :8000 -t 2>/dev/null | xargs -r kill 2>/dev/null
sleep 1
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && PYTHONPATH=. nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/uvicorn-m3a.log 2>&1 &
# 前端 dev:mp-weixin watch 会自动热重新
```

- [ ] **Step 4: 真机验证（人工，~5 分钟）**

WeChat DevTools（Cmd+R 刷新）：
- [ ] profile → 学期卡 → units → U1 Goldilocks → 点 "There be 句型" → 进 kp-content → 看到底部"开始练习（5 题）"按钮 → 截图
- [ ] 点开始 → 进 v2-session，显示第 1 题（单选） → 选 B（或正确选项） → 点提交 → 显示绿色"✓ 答对了" + 解析 → 截图
- [ ] 点下一题 → 显示填空题 → 输入正确答案 → 截图反馈
- [ ] 答错任一题 → 显示红色"✗ 答错了" → 截图
- [ ] 完成 5 题 → 显示"练习完成 共 5 题，对 X 道" → 截图
- [ ] 后端验证错题落库：`docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "SELECT count(*) FROM wrong_questions WHERE source_type='practice';"` ≥ 1

5 张截图 + 错题数发我，全绿就 M3a 收官。

- [ ] **Step 5: D-082 归档**

在 `docs/决策归档.md` 顶部（在 D-081 之前）追加 D-082 条目：

```markdown
## D-082｜V2 M3a 落地：3 类仿真题 + 逐题练习流

**日期：** 2026-06-01
**背景：** D-079 V2 路线 M3 拆出 M3a 优先做"题库 + 单流程练习闭环"。M3b 留题型扩展（完型/阅读/写作）+ 模拟考批量流 + 全 96 KP 预生成。
**结论：**
1. 题型 3 类：**单选 / 填空 / 判断**。enum 加 "判断"（迁移 0009，PG enum ADD VALUE 需 transaction 外）。
2. AI 服务（`question_ai_service.generate_questions`）按 KP 出 5 题，规定题型分布（≥2 单选 + ≥1 填空 + ≥1 判断）；dev mock 固定 5 题供测试 + 前端无 key 跑通。
3. 持久化（`question_service.persist_questions`）按 (kp_id, stem) 去重幂等；`list_questions_by_kp` 返回不含 answer（防作弊）；`submit_attempt` 含 3 套判分（单选/判断 strict equal；填空 trim+lower 后多候选 `|` 分隔匹配），错题自动落 `wrong_questions` + `wrong_question_knowledge_points` 走 V1 错题分析链路。
4. 2 个 API：`GET /questions/kp/{kp_id}/practice-questions?limit=5` + `POST /questions/practice-attempts`。
5. seed CLI 三模式 --kp / --unit / --all-free；初始只跑 4 个 free-unit（实际只小学5上 U1 有真 AI KP），共 8 KP × 5 = 40 题，~$0.1。
6. 前端 1 新页面 `pages/practice/v2-session.vue`（逐题作答+即时反馈+解析）；KP 内容页加"开始练习"按钮入口；3 种题型对应 3 种输入 UI（4 选项卡片 / 输入框 / 对错卡片）。
7. **错题反向链路：** 做错的题写入 wrong_questions（source_type='practice'）+ 链 KP，可被既有 wrong-questions list/detail/AI 分析复用。
**未做（M3b/3c）：** 完型/阅读/写作/连线/如何问 题型；模拟考批量流；96 KP 全量 AI 预生；错题查重（避免同道题反复落库）；做对的题做"标 mastered"反向更新；学情报告按 KP 聚合答题正确率。
**测试：** 11 个新测试（ai 2 + service 6 + api 3），全量 N PASS（待填实数）。
**提交链：** （待填 SHAs）
**影响范围：** 1 alembic 迁移；1 model enum 改；3 新 service；1 新 API 路由；1 CLI 脚本；1 新前端页面 + 1 改动页面 + 1 改动 pages.json + 1 新 API client + 3 新 types；测试 +11；新增 ~40 道仿真题。
```

- [ ] **Step 6: 全量测试 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && \
PYTHONPATH=backend pytest -q 2>&1 | tail -3 && \
git log --oneline -15 && \
git push origin HEAD
```

Expected: 全绿；push 成功

---

## 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 真 AI 生成判分有歧义（填空 answer 候选不全） | 用户答正确选项被判错 | 多候选用 `\|` 分隔，prompt 明确要求；M3b 加题目 quality review 流程 |
| Wrong_questions 表 source_type 字段不存在 | 测试 5 失败 | 实施前先 Read d3_wrong_questions.py 确认字段，没有就改成已存在的 source 类型 |
| ALTER TYPE ADD VALUE 在事务内会失败 | 迁移 0009 报错 | 已用 op.execute("COMMIT") 显式提前提交 |
| 题目重复（同一 KP 多次 seed） | 数据库膨胀 | (kp_id, stem) 去重 |
| 用户作弊（前端篡改 user_answer 也能拿到 explanation） | M3a 不防 | M3a 接受；M3b 加签名 token；MVP 不重要 |

---

## Self-Review

**1. 规格覆盖**
- ✅ 3 题型（单选/填空/判断）：enum 0009 + AI prompt + schema + 判分 + UI
- ✅ 练习流（逐题反馈）：v2-session.vue
- ✅ 8 KP 预生成：seed_questions.py --all-free（实际只有 小学5上 U1 真 AI KP 满足）
- ✅ 错题写入 wrong_questions：question_service.submit_attempt 末尾分支

**2. 占位符检查**
- 无 TBD/TODO
- 所有 code 步骤完整
- D-082 commit SHA 标 "待填" 是正常工序（写归档时还没有 SHA）

**3. 类型一致性**
- `AIGeneratedQuestion / SimQuestionOut / PracticeAttemptIn / PracticeResultOut` 命名一致
- `submit_attempt` 签名 (db, user_id, question_id, user_answer) 在 service / API / test 一致
- `question_type` 值在 enum / schema / 判分函数都用同一组（单选/填空/判断）

---
