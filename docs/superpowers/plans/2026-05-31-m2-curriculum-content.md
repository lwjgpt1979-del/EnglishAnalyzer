# M2: V2 教材内容 AI 生成 + 课程浏览 + 付费墙 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 AI 一次性生成 4 个学期（译林版小学5上下 + 初中7上下）教材内容，前端提供课程浏览（单元 → 知识点 → 4 维度内容），免费用户只能看每学期第 1 单元，其余按已购学期解锁。

**Architecture:** 复用已有 d4（curriculum_units / knowledge_points / unit_knowledge_points / vocabulary_words / curriculum_words）+ d11（knowledge_point_contents）共 6 张表。新增一个 AI 生成 service（DeepSeek，dev mock 复用现有模式）+ 一个 read service（含 paywall）+ 一组 REST API + 3 个前端页面。AI 流水线分两步：先 pilot 1 单元人工验证质量，再批量跑 4 学期。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + AsyncOpenAI（DeepSeek 协议）+ uni-app Vue3 + Pinia + pytest-asyncio

---

## 文件结构

### 后端新增

| 文件 | 责任 |
|---|---|
| `backend/app/schemas/curriculum.py` | Pydantic 输入输出（UnitOut / UnitDetailOut / KnowledgePointOut / KPContentOut / AIGeneratedUnit） |
| `backend/app/services/curriculum_ai_service.py` | 调 DeepSeek 生成 1 个单元的结构化 JSON（含 dev mock） |
| `backend/app/services/curriculum_service.py` | persist_unit() 把 AI JSON upsert 入 6 张表；list_units / get_unit_detail / get_kp_contents（含付费墙） |
| `backend/app/api/v1/curriculum.py` | GET /curriculum/units / /units/{id} / /knowledge-points/{id}/contents |
| `backend/scripts/seed_curriculum.py` | CLI: 遍历 (textbook, grade, semester, unit_no) 调 ai+persist，断点续传 |
| `tests/services/__init__.py` | 新建 services 测试目录 |
| `tests/services/test_curriculum_ai_service.py` | dev mock 输出结构正确性 |
| `tests/services/test_curriculum_service.py` | persist 幂等 + paywall 单元 1 放行/单元 2 拒绝 |
| `tests/api/test_curriculum.py` | 集成测试 3 个端点 |

### 后端修改

| 文件 | 改动 |
|---|---|
| `backend/app/api/v1/router.py` | 注册 curriculum_router |

### 前端新增

| 文件 | 责任 |
|---|---|
| `frontend/miniprogram/src/api/curriculum.ts` | listUnits / getUnitDetail / getKpContents |
| `frontend/miniprogram/src/pages/curriculum/units.vue` | 单元列表，按学期分组，锁标识 |
| `frontend/miniprogram/src/pages/curriculum/unit-detail.vue` | 单元详情：知识点列表 + 词汇表 |
| `frontend/miniprogram/src/pages/curriculum/kp-content.vue` | 单个知识点 4 维度内容切换 |

### 前端修改

| 文件 | 改动 |
|---|---|
| `frontend/miniprogram/src/types/api.ts` | 加 UnitOut / UnitDetailOut / KnowledgePointOut / KPContentOut |
| `frontend/miniprogram/src/pages.json` | 注册 3 个 curriculum 页面 |
| `frontend/miniprogram/src/pages/profile/index.vue` | 学期卡 + "查看课程"按钮 → units 页 |

---

## 数据流概览

```
seed_curriculum.py
  ↓ for each (textbook, grade, semester, unit_no=1..N)
curriculum_ai_service.generate_unit()
  ↓ AsyncOpenAI(deepseek-chat) → JSON
  ↓ AIGeneratedUnit schema 校验
curriculum_service.persist_unit()
  ↓ upsert curriculum_units / knowledge_points / unit_knowledge_points
  ↓ upsert vocabulary_words / curriculum_words
  ↓ upsert knowledge_point_contents（4 维度）
  ↓ commit

前端浏览
  GET /curriculum/units?textbook=&grade=&semester=
    → 列表（unit_no=1 unlocked，其余按 PurchasedSemester 判断）
  GET /curriculum/units/{id}
    → 详情（KP 列表 + 词汇列表，受单元锁约束）
  GET /curriculum/knowledge-points/{id}/contents
    → 4 维度内容（受所属单元锁约束）
```

---

## Task 0: Pydantic Schemas（AI 输入输出 + API 响应）

**Files:**
- Create: `backend/app/schemas/curriculum.py`

- [ ] **Step 1: 创建 schemas/curriculum.py**

```python
"""V2 课程浏览 Pydantic schemas（D-079 / M2）。"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


# ─── AI 生成输出结构（curriculum_ai_service → curriculum_service.persist_unit）─

class AIWordItem(BaseModel):
    word: str
    phonetic: str | None = None
    definitions: list[dict] = Field(
        ..., description="[{pos: 'n.', meaning: '苹果'}, ...]"
    )
    examples: list[str] = []
    difficulty: int = Field(..., ge=1, le=5)
    is_core: bool = True


class AIKnowledgePointItem(BaseModel):
    code: str = Field(..., description="全局唯一编码，例如 'yl-g5s1-u1-kp1'")
    name: str
    category: Literal["grammar", "vocabulary", "reading", "writing", "listening"]
    description: str
    contents: dict[str, str] = Field(
        ...,
        description="key ∈ {listening, dictation, grammar, writing}, value 为 markdown",
    )


class AIGeneratedUnit(BaseModel):
    textbook_version: str
    grade: str
    semester: Literal["上", "下"]
    unit_no: int = Field(..., ge=1, le=20)
    unit_title: str
    knowledge_points: list[AIKnowledgePointItem] = Field(..., min_length=3)
    words: list[AIWordItem] = Field(..., min_length=5)


# ─── API 响应 ───────────────────────────────────────────────────────────────

class UnitOut(BaseModel):
    id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    unit_no: int
    unit_title: str
    locked: bool = Field(..., description="是否需付费解锁（unit_no=1 永远 false）")
    kp_count: int = 0


class KnowledgePointOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    description: str | None = None


class WordOut(BaseModel):
    id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] = []
    difficulty: int


class UnitDetailOut(UnitOut):
    knowledge_points: list[KnowledgePointOut] = []
    words: list[WordOut] = []


class KPContentOut(BaseModel):
    dimension: str  # listening | dictation | grammar | writing
    content_md: str
    audio_url: str | None = None
```

- [ ] **Step 2: 验证 import**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && python -c "from backend.app.schemas.curriculum import AIGeneratedUnit, UnitDetailOut; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/curriculum.py
git commit -m "feat(m2): add curriculum pydantic schemas for AI gen + browse"
```

---

## Task 1: AI 生成 Service（含 dev mock）

**Files:**
- Create: `backend/app/services/curriculum_ai_service.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/test_curriculum_ai_service.py`

- [ ] **Step 1: 创建 tests/services/__init__.py**

```python
```

- [ ] **Step 2: 写失败测试**

Create `tests/services/test_curriculum_ai_service.py`:

```python
"""curriculum_ai_service dev mock 测试。

dev mock（DEEPSEEK_API_KEY 以 sk-placeholder 开头）下返回固定结构，
让 persist + 前端开发不需要真实 API key。
"""
from __future__ import annotations

import pytest

from app.services.curriculum_ai_service import generate_unit


@pytest.mark.asyncio
async def test_dev_mock_returns_valid_structure():
    """dev mock 必须返回符合 AIGeneratedUnit 的完整结构。"""
    unit = await generate_unit(
        textbook_version="译林版",
        grade="小学5年级",
        semester="上",
        unit_no=1,
    )

    assert unit.textbook_version == "译林版"
    assert unit.grade == "小学5年级"
    assert unit.semester == "上"
    assert unit.unit_no == 1
    assert unit.unit_title  # 非空
    assert len(unit.knowledge_points) >= 3
    assert len(unit.words) >= 5

    # 知识点 4 维度都得有
    for kp in unit.knowledge_points:
        assert set(kp.contents.keys()) == {"listening", "dictation", "grammar", "writing"}
        assert all(v.strip() for v in kp.contents.values())
        # code 必须包含 unit 标识方便幂等 upsert
        assert "u1" in kp.code or str(unit.unit_no) in kp.code


@pytest.mark.asyncio
async def test_dev_mock_different_units_have_different_titles():
    """不同 unit_no 的 mock 结果应该可区分（避免幂等 upsert 把所有单元合并）。"""
    u1 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1)
    u2 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=2)
    assert u1.unit_title != u2.unit_title
    assert u1.knowledge_points[0].code != u2.knowledge_points[0].code
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_curriculum_ai_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.curriculum_ai_service'`

- [ ] **Step 4: 实现 curriculum_ai_service.py**

Create `backend/app/services/curriculum_ai_service.py`:

```python
"""V2 课程内容 AI 生成 service（D-079 / M2）。

调 DeepSeek（OpenAI 兼容协议）生成单个单元的完整结构化内容。
dev 模式（DEEPSEEK_API_KEY 以 sk-placeholder 开头）返回 mock 数据，
让 persist + 前端流程在无 API key 时可完整跑通。
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.curriculum import AIGeneratedUnit

_SYSTEM_PROMPT = (
    "你是资深英语教材编辑，擅长按教材大纲为每个单元拆解知识点并生成教学解读。"
    "请严格按 JSON 格式输出，不要任何 markdown 代码块或额外文字。"
)

_USER_PROMPT_TEMPLATE = """请为以下教材单元生成完整教学内容。

教材：{textbook_version}
年级：{grade}
学期：{semester}
单元号：{unit_no}

要求：
1. 推断该单元的标题（unit_title），符合该教材实际编排
2. 列出 5-10 个核心知识点（grammar/vocabulary/reading/writing/listening 任一类）
3. 每个知识点提供 4 维度教学内容（listening/dictation/grammar/writing）markdown
4. 列出 10-20 个核心单词
5. code 字段格式：'yl-g{grade_short}s{sem_short}-u{unit_no}-kp{idx}'，必须全局唯一

返回纯 JSON（不要 markdown）：
{{
  "textbook_version": "{textbook_version}",
  "grade": "{grade}",
  "semester": "{semester}",
  "unit_no": {unit_no},
  "unit_title": "...",
  "knowledge_points": [
    {{
      "code": "yl-g5s1-u1-kp1",
      "name": "一般现在时第三人称单数",
      "category": "grammar",
      "description": "...",
      "contents": {{
        "listening": "## 听力要点\\n...",
        "dictation": "## 听写训练\\n...",
        "grammar": "## 语法解析\\n...",
        "writing": "## 写作应用\\n..."
      }}
    }}
  ],
  "words": [
    {{
      "word": "apple",
      "phonetic": "/ˈæpəl/",
      "definitions": [{{"pos": "n.", "meaning": "苹果"}}],
      "examples": ["I eat an apple every day."],
      "difficulty": 1,
      "is_core": true
    }}
  ]
}}"""


def _is_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _make_mock_unit(
    textbook_version: str, grade: str, semester: str, unit_no: int
) -> AIGeneratedUnit:
    """dev mock：生成结构合法但内容是占位文本的单元。"""
    grade_short = "5" if "5" in grade else "7"
    sem_short = "1" if semester == "上" else "2"
    prefix = f"yl-g{grade_short}s{sem_short}-u{unit_no}"

    return AIGeneratedUnit(
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,  # type: ignore[arg-type]
        unit_no=unit_no,
        unit_title=f"Unit {unit_no} Mock Title ({grade}{semester})",
        knowledge_points=[
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp1",
                "name": f"知识点 {unit_no}-1（mock 语法）",
                "category": "grammar",
                "description": "占位描述：dev mock 数据",
                "contents": {
                    "listening": f"## 听力要点（U{unit_no}-KP1）\n这是 mock 听力解读。",
                    "dictation": f"## 听写训练（U{unit_no}-KP1）\n这是 mock 听写要点。",
                    "grammar": f"## 语法解析（U{unit_no}-KP1）\n这是 mock 语法讲解。",
                    "writing": f"## 写作应用（U{unit_no}-KP1）\n这是 mock 写作举例。",
                },
            },
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp2",
                "name": f"知识点 {unit_no}-2（mock 词汇）",
                "category": "vocabulary",
                "description": "占位描述",
                "contents": {
                    "listening": "## 听力\nmock",
                    "dictation": "## 听写\nmock",
                    "grammar": "## 语法\nmock",
                    "writing": "## 写作\nmock",
                },
            },
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp3",
                "name": f"知识点 {unit_no}-3（mock 阅读）",
                "category": "reading",
                "description": "占位描述",
                "contents": {
                    "listening": "## 听力\nmock",
                    "dictation": "## 听写\nmock",
                    "grammar": "## 语法\nmock",
                    "writing": "## 写作\nmock",
                },
            },
        ],
        words=[
            {  # type: ignore[list-item]
                "word": f"word{unit_no}_{i}",
                "phonetic": None,
                "definitions": [{"pos": "n.", "meaning": f"mock 释义{i}"}],
                "examples": [f"Mock example {i}."],
                "difficulty": 1,
                "is_core": True,
            }
            for i in range(1, 6)
        ],
    )


async def generate_unit(
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
) -> AIGeneratedUnit:
    """生成 1 个单元的完整结构化内容。dev mock 或真实 DeepSeek 调用。"""
    if _is_dev_mode():
        return _make_mock_unit(textbook_version, grade, semester, unit_no)

    grade_short = "5" if "5" in grade else "7"
    sem_short = "1" if semester == "上" else "2"
    prompt = _USER_PROMPT_TEMPLATE.format(
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
        unit_no=unit_no,
        grade_short=grade_short,
        sem_short=sem_short,
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
        raise AppError(code=502, message=f"AI 课程生成失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message=f"AI 返回非 JSON：{raw[:200]}") from exc

    try:
        return AIGeneratedUnit(**data)
    except Exception as exc:
        raise AppError(code=500, message=f"AI 输出 schema 不符：{exc}") from exc
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_curriculum_ai_service.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/curriculum_ai_service.py tests/services/
git commit -m "feat(m2): add curriculum AI generation service with dev mock"
```

---

## Task 2: Persist Service（AI JSON → 6 张表 upsert）

**Files:**
- Create: `backend/app/services/curriculum_service.py`
- Create: `tests/services/test_curriculum_service.py`

- [ ] **Step 1: 写失败测试**

Create `tests/services/test_curriculum_service.py`:

```python
"""curriculum_service.persist_unit 幂等性 + paywall 测试。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.d4_knowledge import (
    CurriculumUnit,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.models.d11_v2_curriculum import KnowledgePointContent
from app.services import curriculum_ai_service, curriculum_service


@pytest.mark.asyncio
async def test_persist_unit_creates_all_6_tables(db_session):
    """persist_unit 一次性写入 6 张表。"""
    unit = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1,
    )

    await curriculum_service.persist_unit(db_session, ai_unit=unit)
    await db_session.flush()

    # curriculum_units
    cu = (await db_session.execute(
        select(CurriculumUnit).where(CurriculumUnit.unit_no == 1)
    )).scalar_one()
    assert cu.unit_title == unit.unit_title

    # knowledge_points
    kps = (await db_session.execute(select(KnowledgePoint))).scalars().all()
    assert len(kps) >= 3

    # unit_knowledge_points link
    links = (await db_session.execute(
        select(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id == cu.id)
    )).scalars().all()
    assert len(links) == len(kps)

    # vocabulary_words
    words = (await db_session.execute(select(VocabularyWord))).scalars().all()
    assert len(words) >= 5

    # curriculum_words link
    cw = (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id)
    )).scalars().all()
    assert len(cw) == len(words)

    # knowledge_point_contents: 每 KP × 4 维度
    contents = (await db_session.execute(select(KnowledgePointContent))).scalars().all()
    assert len(contents) == len(kps) * 4


@pytest.mark.asyncio
async def test_persist_unit_idempotent(db_session):
    """二次 persist 不应产生重复行。"""
    unit = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1,
    )
    await curriculum_service.persist_unit(db_session, ai_unit=unit)
    await db_session.flush()
    count1 = len((await db_session.execute(select(KnowledgePoint))).scalars().all())

    # 二次 persist 相同内容
    await curriculum_service.persist_unit(db_session, ai_unit=unit)
    await db_session.flush()
    count2 = len((await db_session.execute(select(KnowledgePoint))).scalars().all())

    assert count1 == count2  # 没增加


@pytest.mark.asyncio
async def test_unit_lock_first_unit_always_free(db_session):
    """unit_no=1 永远返回 locked=False，无论是否买学期。"""
    fake_user = uuid.uuid4()
    locked = await curriculum_service.is_unit_locked(
        db_session,
        user_id=fake_user,
        textbook_version="译林版", grade="小学5年级", semester="上",
        unit_no=1,
    )
    assert locked is False


@pytest.mark.asyncio
async def test_unit_lock_other_units_locked_without_semester(db_session):
    """unit_no>1 且无 PurchasedSemester 时 locked=True。"""
    fake_user = uuid.uuid4()
    locked = await curriculum_service.is_unit_locked(
        db_session,
        user_id=fake_user,
        textbook_version="译林版", grade="小学5年级", semester="上",
        unit_no=2,
    )
    assert locked is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_curriculum_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 curriculum_service.py**

Create `backend/app/services/curriculum_service.py`:

```python
"""V2 课程浏览 service（D-079 / M2）。

职责：
1. persist_unit() — 把 curriculum_ai_service 输出 upsert 入 6 张表（幂等）
2. is_unit_locked() — unit_no=1 永远免费，其余按 PurchasedSemester 判断
3. list_units / get_unit_detail / get_kp_contents — 给 API 用的 read 函数
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import (
    CurriculumUnit,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.models.d11_v2_curriculum import KnowledgePointContent
from app.schemas.curriculum import (
    AIGeneratedUnit,
    KnowledgePointOut,
    KPContentOut,
    UnitDetailOut,
    UnitOut,
    WordOut,
)
from app.services import semester_service


# ─── Persist ────────────────────────────────────────────────────────────────

async def persist_unit(db: AsyncSession, *, ai_unit: AIGeneratedUnit) -> CurriculumUnit:
    """把 AI 生成的单元结构 upsert 入 6 张表，返回 CurriculumUnit。幂等。"""
    # 1. curriculum_units（按 textbook+grade+semester+unit_no 唯一）
    cu_q = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == ai_unit.textbook_version,
            CurriculumUnit.grade == ai_unit.grade,
            CurriculumUnit.semester == ai_unit.semester,
            CurriculumUnit.unit_no == ai_unit.unit_no,
        )
    )
    cu = cu_q.scalar_one_or_none()
    if cu is None:
        cu = CurriculumUnit(
            id=uuid.uuid4(),
            textbook_version=ai_unit.textbook_version,
            grade=ai_unit.grade,
            semester=ai_unit.semester,  # type: ignore[arg-type]
            unit_no=ai_unit.unit_no,
            unit_title=ai_unit.unit_title,
        )
        db.add(cu)
        await db.flush()
    else:
        cu.unit_title = ai_unit.unit_title

    # 2. knowledge_points + 3. unit_knowledge_points + 4. knowledge_point_contents
    for kp_in in ai_unit.knowledge_points:
        kp_q = await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.code == kp_in.code)
        )
        kp = kp_q.scalar_one_or_none()
        if kp is None:
            kp = KnowledgePoint(
                id=uuid.uuid4(),
                code=kp_in.code,
                name=kp_in.name,
                category=kp_in.category,  # type: ignore[arg-type]
                description=kp_in.description,
                applicable_grades=[ai_unit.grade],
                applicable_textbooks=[ai_unit.textbook_version],
            )
            db.add(kp)
            await db.flush()
        else:
            kp.name = kp_in.name
            kp.description = kp_in.description

        # link
        link_q = await db.execute(
            select(UnitKnowledgePoint).where(
                UnitKnowledgePoint.unit_id == cu.id,
                UnitKnowledgePoint.knowledge_point_id == kp.id,
            )
        )
        if link_q.scalar_one_or_none() is None:
            db.add(UnitKnowledgePoint(unit_id=cu.id, knowledge_point_id=kp.id))

        # contents 4 维度
        for dim, md in kp_in.contents.items():
            c_q = await db.execute(
                select(KnowledgePointContent).where(
                    KnowledgePointContent.knowledge_point_id == kp.id,
                    KnowledgePointContent.dimension == dim,
                )
            )
            kpc = c_q.scalar_one_or_none()
            if kpc is None:
                db.add(KnowledgePointContent(
                    id=uuid.uuid4(),
                    knowledge_point_id=kp.id,
                    dimension=dim,  # type: ignore[arg-type]
                    content_md=md,
                    status="published",
                    generated_by="ai_full",
                ))
            else:
                kpc.content_md = md

    # 5. vocabulary_words + 6. curriculum_words
    for w_in in ai_unit.words:
        w_q = await db.execute(
            select(VocabularyWord).where(VocabularyWord.word == w_in.word)
        )
        w = w_q.scalar_one_or_none()
        if w is None:
            w = VocabularyWord(
                id=uuid.uuid4(),
                word=w_in.word,
                phonetic=w_in.phonetic,
                definitions=w_in.definitions,
                examples=w_in.examples,
                difficulty=w_in.difficulty,
            )
            db.add(w)
            await db.flush()

        cw_q = await db.execute(
            select(CurriculumWord).where(
                CurriculumWord.unit_id == cu.id,
                CurriculumWord.word_id == w.id,
            )
        )
        if cw_q.scalar_one_or_none() is None:
            db.add(CurriculumWord(
                unit_id=cu.id,
                word_id=w.id,
                is_core=w_in.is_core,
            ))

    return cu


# ─── Paywall ────────────────────────────────────────────────────────────────

async def is_unit_locked(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
) -> bool:
    """unit_no=1 永远免费；其余按 PurchasedSemester 判断。"""
    if unit_no == 1:
        return False
    ok, _, _ = await semester_service.query_access(
        db, user_id=user_id,
        textbook_version=textbook_version, grade=grade, semester=semester,
    )
    return not ok


# ─── Read APIs ──────────────────────────────────────────────────────────────

async def list_units(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
) -> list[UnitOut]:
    r = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
        ).order_by(CurriculumUnit.unit_no)
    )
    units = list(r.scalars().all())

    out: list[UnitOut] = []
    for u in units:
        kp_count = len(
            (await db.execute(
                select(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id == u.id)
            )).scalars().all()
        )
        locked = await is_unit_locked(
            db, user_id=user_id,
            textbook_version=textbook_version, grade=grade, semester=semester,
            unit_no=u.unit_no,
        )
        out.append(UnitOut(
            id=u.id,
            textbook_version=u.textbook_version,
            grade=u.grade,
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title,
            locked=locked,
            kp_count=kp_count,
        ))
    return out


async def get_unit_detail(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    unit_id: uuid.UUID,
) -> UnitDetailOut:
    u = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if u is None:
        raise AppError(code=404, message="单元不存在")

    locked = await is_unit_locked(
        db, user_id=user_id,
        textbook_version=u.textbook_version, grade=u.grade, semester=str(u.semester),
        unit_no=u.unit_no,
    )
    if locked:
        raise AppError(code=403, message="该单元需购买学期会员后解锁")

    # KP list
    kp_rows = (await db.execute(
        select(KnowledgePoint).join(
            UnitKnowledgePoint,
            UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
        ).where(UnitKnowledgePoint.unit_id == u.id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.code)
    )).scalars().all()
    kps = [KnowledgePointOut(
        id=kp.id, code=kp.code, name=kp.name,
        category=str(kp.category), description=kp.description,
    ) for kp in kp_rows]

    # Word list
    w_rows = (await db.execute(
        select(VocabularyWord).join(
            CurriculumWord, CurriculumWord.word_id == VocabularyWord.id,
        ).where(CurriculumWord.unit_id == u.id)
        .order_by(CurriculumWord.sort_order, VocabularyWord.word)
    )).scalars().all()
    words = [WordOut(
        id=w.id, word=w.word, phonetic=w.phonetic,
        definitions=w.definitions or [], difficulty=w.difficulty,
    ) for w in w_rows]

    return UnitDetailOut(
        id=u.id,
        textbook_version=u.textbook_version,
        grade=u.grade,
        semester=str(u.semester),
        unit_no=u.unit_no,
        unit_title=u.unit_title,
        locked=False,
        kp_count=len(kps),
        knowledge_points=kps,
        words=words,
    )


async def get_kp_contents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    kp_id: uuid.UUID,
) -> list[KPContentOut]:
    """返回某知识点的 4 维度内容。受其所属单元的锁约束。"""
    # 找到该 KP 所属的任一单元（取 unit_no 最小的代表）
    cu = (await db.execute(
        select(CurriculumUnit).join(
            UnitKnowledgePoint,
            UnitKnowledgePoint.unit_id == CurriculumUnit.id,
        ).where(UnitKnowledgePoint.knowledge_point_id == kp_id)
        .order_by(CurriculumUnit.unit_no)
    )).scalars().first()
    if cu is None:
        raise AppError(code=404, message="知识点未关联任何单元")

    locked = await is_unit_locked(
        db, user_id=user_id,
        textbook_version=cu.textbook_version, grade=cu.grade,
        semester=str(cu.semester), unit_no=cu.unit_no,
    )
    if locked:
        raise AppError(code=403, message="该知识点所属单元需购买学期会员后解锁")

    contents = (await db.execute(
        select(KnowledgePointContent).where(
            KnowledgePointContent.knowledge_point_id == kp_id,
        )
    )).scalars().all()
    return [KPContentOut(
        dimension=str(c.dimension),
        content_md=c.content_md,
        audio_url=c.audio_url,
    ) for c in contents]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/services/test_curriculum_service.py -v`
Expected: PASS（4 个测试）

> 注意：`db_session` fixture 应已在 `tests/conftest.py` 提供。如未提供需新建。先尝试运行，若 fixture 缺失再补。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/curriculum_service.py tests/services/test_curriculum_service.py
git commit -m "feat(m2): add curriculum_service persist + paywall logic"
```

---

## Task 3: API Endpoints

**Files:**
- Create: `backend/app/api/v1/curriculum.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `tests/api/test_curriculum.py`

- [ ] **Step 1: 写失败测试**

Create `tests/api/test_curriculum.py`:

```python
"""curriculum API 端点集成测试。"""
from __future__ import annotations

import pytest

from app.services import curriculum_ai_service, curriculum_service


@pytest.mark.asyncio
async def test_list_units_returns_locked_field(auth_client, db_session):
    """GET /curriculum/units 必须返回 locked 字段，unit_no=1 永远 false。"""
    # 准备：seed 两个单元
    for unit_no in [1, 2]:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="小学5年级", semester="上",
            unit_no=unit_no,
        )
        await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.commit()

    resp = await auth_client.get(
        "/api/v1/curriculum/units",
        params={"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    units = body["data"]
    assert len(units) >= 2

    u1 = next(u for u in units if u["unit_no"] == 1)
    u2 = next(u for u in units if u["unit_no"] == 2)
    assert u1["locked"] is False
    assert u2["locked"] is True


@pytest.mark.asyncio
async def test_get_unit_detail_403_when_locked(auth_client, db_session):
    """unit_no=2 详情对无学期用户返回 403。"""
    ai = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=2,
    )
    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.commit()

    resp = await auth_client.get(f"/api/v1/curriculum/units/{cu.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_unit_detail_200_for_unit_1(auth_client, db_session):
    """unit_no=1 详情免费打开，返回 KP 列表 + 词汇列表。"""
    ai = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1,
    )
    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.commit()

    resp = await auth_client.get(f"/api/v1/curriculum/units/{cu.id}")
    assert resp.status_code == 200
    detail = resp.json()["data"]
    assert detail["unit_no"] == 1
    assert detail["locked"] is False
    assert len(detail["knowledge_points"]) >= 3
    assert len(detail["words"]) >= 5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/api/test_curriculum.py -v`
Expected: FAIL with 404（路由未注册）

- [ ] **Step 3: 实现 API endpoints**

Create `backend/app/api/v1/curriculum.py`:

```python
"""V2 课程浏览 API（D-079 / M2）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.services import curriculum_service

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("/units")
async def list_units(
    textbook_version: str = Query(...),
    grade: str = Query(...),
    semester: str = Query(..., description="上 / 下"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await curriculum_service.list_units(
        db,
        user_id=current_user.id,
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
    )
    return make_ok([i.model_dump(mode="json") for i in items])


@router.get("/units/{unit_id}")
async def get_unit_detail(
    unit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await curriculum_service.get_unit_detail(
        db, user_id=current_user.id, unit_id=unit_id,
    )
    return make_ok(detail.model_dump(mode="json"))


@router.get("/knowledge-points/{kp_id}/contents")
async def get_kp_contents(
    kp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contents = await curriculum_service.get_kp_contents(
        db, user_id=current_user.id, kp_id=kp_id,
    )
    return make_ok([c.model_dump(mode="json") for c in contents])
```

- [ ] **Step 4: 注册路由**

Edit `backend/app/api/v1/router.py` — 加 import 和 include_router：

```python
from app.api.v1.curriculum import router as curriculum_router  # 新增 import
# ... 现有代码 ...
v1_router.include_router(curriculum_router)  # 加在 semesters_router 附近
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest tests/api/test_curriculum.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: 运行全部测试确保未破坏**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend pytest -q`
Expected: 全绿（包含原有 237+ 测试 + 新增 9 个）

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/curriculum.py backend/app/api/v1/router.py tests/api/test_curriculum.py
git commit -m "feat(m2): add curriculum API endpoints (list/detail/kp-contents)"
```

---

## Task 4: CLI Seed 脚本（断点续传，dev mock + 真实 API 都能跑）

**Files:**
- Create: `backend/scripts/seed_curriculum.py`

- [ ] **Step 1: 创建 seed 脚本**

Create `backend/scripts/seed_curriculum.py`:

```python
"""V2 课程内容批量 seed 脚本（D-079 / M2）。

用法：
  # dev mock 跑 1 个单元（pilot）
  python backend/scripts/seed_curriculum.py --textbook 译林版 --grade 小学5年级 --semester 上 --unit 1

  # dev mock 跑 1 个学期（10 个单元）
  python backend/scripts/seed_curriculum.py --textbook 译林版 --grade 小学5年级 --semester 上 --units 1-10

  # 真实 API 跑 4 个学期全部
  DEEPSEEK_API_KEY=sk-real-key python backend/scripts/seed_curriculum.py --all

幂等：相同 (textbook, grade, semester, unit_no) 多次跑只会 upsert，不会重复。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本能直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_maker  # noqa: E402
from app.models.d4_knowledge import CurriculumUnit  # noqa: E402
from app.services import curriculum_ai_service, curriculum_service  # noqa: E402


FULL_SEMESTERS = [
    ("译林版", "小学5年级", "上"),
    ("译林版", "小学5年级", "下"),
    ("译林版", "初中7年级", "上"),
    ("译林版", "初中7年级", "下"),
]
UNITS_PER_SEMESTER = 8  # 默认每学期 8 单元


async def seed_one(textbook: str, grade: str, semester: str, unit_no: int) -> None:
    async with async_session_maker() as db:
        # 断点续传：已存在的单元跳过
        existing = (await db.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == textbook,
                CurriculumUnit.grade == grade,
                CurriculumUnit.semester == semester,
                CurriculumUnit.unit_no == unit_no,
            )
        )).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] {textbook} {grade} {semester} U{unit_no} 已存在")
            return

        print(f"  [gen]  {textbook} {grade} {semester} U{unit_no} …", end=" ", flush=True)
        ai = await curriculum_ai_service.generate_unit(
            textbook_version=textbook, grade=grade, semester=semester, unit_no=unit_no,
        )
        await curriculum_service.persist_unit(db, ai_unit=ai)
        await db.commit()
        print(f"✓ {len(ai.knowledge_points)} KP, {len(ai.words)} 词")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--textbook", default="译林版")
    p.add_argument("--grade")
    p.add_argument("--semester")
    p.add_argument("--unit", type=int, help="单个单元号")
    p.add_argument("--units", help="范围，例如 1-10")
    p.add_argument("--all", action="store_true", help="跑全部 4 学期 × 8 单元")
    args = p.parse_args()

    if args.all:
        for textbook, grade, semester in FULL_SEMESTERS:
            print(f"\n=== {textbook} {grade} {semester} ===")
            for unit_no in range(1, UNITS_PER_SEMESTER + 1):
                await seed_one(textbook, grade, semester, unit_no)
        print("\n✓ 全部完成")
        return

    if not (args.grade and args.semester):
        p.error("--grade 和 --semester 必填（除非用 --all）")

    if args.unit:
        await seed_one(args.textbook, args.grade, args.semester, args.unit)
    elif args.units:
        lo, hi = (int(x) for x in args.units.split("-"))
        for unit_no in range(lo, hi + 1):
            await seed_one(args.textbook, args.grade, args.semester, unit_no)
    else:
        p.error("必须指定 --unit 或 --units 或 --all")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: dev mock 跑 1 个 pilot 单元**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --unit 1`
Expected: `[gen]  译林版 小学5年级 上 U1 … ✓ 3 KP, 5 词`

- [ ] **Step 3: 验证幂等（再跑一次应该 skip）**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --unit 1`
Expected: `[skip] 译林版 小学5年级 上 U1 已存在`

- [ ] **Step 4: 跑 dev mock 全套（4 学期 × 8 单元 = 32 单元）**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python backend/scripts/seed_curriculum.py --all`
Expected: 4 段输出，每段 8 单元，dev mock 下 < 30 秒完成

- [ ] **Step 5: 数据库行数核验**

Run: `docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "SELECT count(*) AS units FROM curriculum_units; SELECT count(*) AS kps FROM knowledge_points; SELECT count(*) AS contents FROM knowledge_point_contents; SELECT count(*) AS words FROM vocabulary_words;"`
Expected: units=32, kps=96 (32×3), contents=384 (96×4), words=160 (32×5)

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/seed_curriculum.py
git commit -m "feat(m2): add seed_curriculum CLI script with resumable batch mode"
```

---

## Task 5: 前端 API + 类型

**Files:**
- Create: `frontend/miniprogram/src/api/curriculum.ts`
- Modify: `frontend/miniprogram/src/types/api.ts`

- [ ] **Step 1: 加类型到 types/api.ts（追加到文件末尾）**

```typescript
// ─── V2 课程浏览（D-079 / M2）──
export interface UnitOut {
  id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  locked: boolean
  kp_count: number
}

export interface KnowledgePointOut {
  id: string
  code: string
  name: string
  category: string
  description: string | null
}

export interface WordOut {
  id: string
  word: string
  phonetic: string | null
  definitions: Array<{ pos?: string; meaning: string }>
  difficulty: number
}

export interface UnitDetailOut extends UnitOut {
  knowledge_points: KnowledgePointOut[]
  words: WordOut[]
}

export interface KPContentOut {
  dimension: string
  content_md: string
  audio_url: string | null
}
```

- [ ] **Step 2: 创建 api/curriculum.ts**

```typescript
import { request } from '@/utils/request'
import type { UnitOut, UnitDetailOut, KPContentOut } from '@/types/api'

export function listUnits(
  textbook_version: string, grade: string, semester: string,
): Promise<UnitOut[]> {
  return request<UnitOut[]>('/api/v1/curriculum/units', {
    method: 'GET',
    data: { textbook_version, grade, semester },
  })
}

export function getUnitDetail(unitId: string): Promise<UnitDetailOut> {
  return request<UnitDetailOut>(`/api/v1/curriculum/units/${unitId}`, {
    method: 'GET',
  })
}

export function getKpContents(kpId: string): Promise<KPContentOut[]> {
  return request<KPContentOut[]>(
    `/api/v1/curriculum/knowledge-points/${kpId}/contents`,
    { method: 'GET' },
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/src/api/curriculum.ts frontend/miniprogram/src/types/api.ts
git commit -m "feat(m2): add curriculum frontend API client + types"
```

---

## Task 6: 前端单元列表页

**Files:**
- Create: `frontend/miniprogram/src/pages/curriculum/units.vue`
- Modify: `frontend/miniprogram/src/pages.json`

- [ ] **Step 1: 创建 units.vue**

```vue
<template>
  <view class="page">
    <view class="header">
      <text class="header-title">{{ textbookVersion }} · {{ grade }} · {{ semester }}</text>
      <text class="header-sub">共 {{ units.length }} 个单元，前 1 个免费</text>
    </view>

    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!units.length" class="empty">该学期暂无内容</view>

    <view v-else class="unit-list">
      <view
        v-for="u in units"
        :key="u.id"
        class="unit-card"
        :class="{ locked: u.locked }"
        @tap="onTapUnit(u)"
      >
        <view class="unit-no-badge">U{{ u.unit_no }}</view>
        <view class="unit-body">
          <text class="unit-title">{{ u.unit_title }}</text>
          <text class="unit-meta">{{ u.kp_count }} 个知识点</text>
        </view>
        <view class="unit-status">
          <text v-if="u.locked" class="lock-icon">🔒</text>
          <text v-else class="open-icon">›</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listUnits } from '@/api/curriculum'
import type { UnitOut } from '@/types/api'

const textbookVersion = ref('')
const grade = ref('')
const semester = ref('')
const units = ref<UnitOut[]>([])
const loading = ref(true)

onLoad(async (q: any) => {
  textbookVersion.value = q.textbook || '译林版'
  grade.value = q.grade || '小学5年级'
  semester.value = q.semester || '上'
  try {
    units.value = await listUnits(textbookVersion.value, grade.value, semester.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function onTapUnit(u: UnitOut) {
  if (u.locked) {
    uni.showModal({
      title: '需要解锁',
      content: `购买《${textbookVersion.value} ${grade.value} ${semester.value}》学期会员后可学习所有单元。`,
      confirmText: '去个人中心',
      success: (r) => {
        if (r.confirm) uni.switchTab({ url: '/pages/profile/index' })
      },
    })
    return
  }
  uni.navigateTo({ url: `/pages/curriculum/unit-detail?id=${u.id}` })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.header { padding: 12rpx 0 24rpx; }
.header-title { display: block; font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); }
.header-sub { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.empty { text-align: center; color: var(--c-text-hint); padding: 80rpx 0; font-size: 28rpx; }
.unit-list { display: flex; flex-direction: column; gap: 16rpx; }
.unit-card {
  background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx;
  box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04);
  display: flex; align-items: center; gap: 20rpx;
}
.unit-card.locked { opacity: .65; }
.unit-no-badge {
  background: var(--c-primary); color: var(--c-ink);
  border-radius: var(--r-md); padding: 8rpx 16rpx;
  font-size: 28rpx; font-weight: 800; min-width: 64rpx; text-align: center;
}
.unit-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.unit-title { font-size: 30rpx; font-weight: 600; color: var(--c-ink); }
.unit-meta { font-size: 24rpx; color: var(--c-text-second); }
.unit-status { font-size: 32rpx; color: var(--c-text-hint); }
.lock-icon { font-size: 36rpx; }
</style>
```

- [ ] **Step 2: 注册 pages.json**

Modify `frontend/miniprogram/src/pages.json` — 在 `pages` 数组里追加（在 relative pages 后面）：

```json
{ "path": "pages/curriculum/units", "style": { "navigationBarTitleText": "课程单元" } },
{ "path": "pages/curriculum/unit-detail", "style": { "navigationBarTitleText": "单元详情" } },
{ "path": "pages/curriculum/kp-content", "style": { "navigationBarTitleText": "知识点" } },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/src/pages/curriculum/units.vue frontend/miniprogram/src/pages.json
git commit -m "feat(m2): add curriculum units list page"
```

---

## Task 7: 前端单元详情页 + 知识点内容页

**Files:**
- Create: `frontend/miniprogram/src/pages/curriculum/unit-detail.vue`
- Create: `frontend/miniprogram/src/pages/curriculum/kp-content.vue`

- [ ] **Step 1: 创建 unit-detail.vue**

```vue
<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="detail">
      <view class="header">
        <text class="badge">U{{ detail.unit_no }}</text>
        <text class="title">{{ detail.unit_title }}</text>
        <text class="meta">{{ detail.knowledge_points.length }} 知识点 · {{ detail.words.length }} 词</text>
      </view>

      <view class="card">
        <view class="card-title">知识点</view>
        <view
          v-for="kp in detail.knowledge_points"
          :key="kp.id"
          class="kp-row"
          @tap="goKp(kp.id)"
        >
          <view class="kp-body">
            <text class="kp-name">{{ kp.name }}</text>
            <text class="kp-cat">{{ catLabel(kp.category) }}</text>
          </view>
          <text class="chevron">›</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">词汇 ({{ detail.words.length }})</view>
        <view v-for="w in detail.words" :key="w.id" class="word-row">
          <text class="word-en">{{ w.word }}</text>
          <text v-if="w.phonetic" class="word-ph">{{ w.phonetic }}</text>
          <text class="word-cn">{{ definitionText(w.definitions) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getUnitDetail } from '@/api/curriculum'
import type { UnitDetailOut, WordOut } from '@/types/api'

const detail = ref<UnitDetailOut | null>(null)
const loading = ref(true)

onLoad(async (q: any) => {
  try {
    detail.value = await getUnitDetail(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
  } finally {
    loading.value = false
  }
})

function goKp(id: string) {
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${id}` })
}
function catLabel(c: string): string {
  return ({ grammar: '语法', vocabulary: '词汇', reading: '阅读', writing: '写作', listening: '听力' } as any)[c] || c
}
function definitionText(defs: WordOut['definitions']): string {
  return defs.map(d => (d.pos ? `${d.pos} ${d.meaning}` : d.meaning)).join('；')
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.header { display: flex; align-items: center; gap: 16rpx; padding: 12rpx 0 24rpx; }
.badge { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-md); padding: 6rpx 14rpx; font-size: 26rpx; font-weight: 800; }
.title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); flex: 1; }
.meta { font-size: 22rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 16rpx; color: var(--c-ink); }
.kp-row { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.kp-row:last-child { border-bottom: none; }
.kp-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.kp-name { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.kp-cat { font-size: 22rpx; color: var(--c-text-second); }
.chevron { color: var(--c-text-hint); font-size: 32rpx; }
.word-row { display: flex; align-items: baseline; gap: 12rpx; padding: 12rpx 0; border-bottom: 1rpx dashed var(--c-border); }
.word-row:last-child { border-bottom: none; }
.word-en { font-size: 28rpx; font-weight: 700; color: var(--c-ink); min-width: 160rpx; }
.word-ph { font-size: 22rpx; color: var(--c-text-hint); }
.word-cn { flex: 1; font-size: 24rpx; color: var(--c-text-body); }
</style>
```

- [ ] **Step 2: 创建 kp-content.vue**

```vue
<template>
  <view class="page">
    <view class="tabs">
      <view
        v-for="d in dims" :key="d.key"
        class="tab" :class="{ active: activeDim === d.key }"
        @tap="activeDim = d.key"
      >{{ d.label }}</view>
    </view>

    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!currentContent" class="empty">该维度暂无内容</view>
    <scroll-view v-else scroll-y class="content">
      <text class="md">{{ currentContent.content_md }}</text>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getKpContents } from '@/api/curriculum'
import type { KPContentOut } from '@/types/api'

const dims = [
  { key: 'listening', label: '听力' },
  { key: 'dictation', label: '听写' },
  { key: 'grammar', label: '语法' },
  { key: 'writing', label: '写作' },
]
const contents = ref<KPContentOut[]>([])
const activeDim = ref('grammar')
const loading = ref(true)

const currentContent = computed(
  () => contents.value.find(c => c.dimension === activeDim.value) || null,
)

onLoad(async (q: any) => {
  try {
    contents.value = await getKpContents(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 0; background: var(--c-bg-page); min-height: 100vh; display: flex; flex-direction: column; }
.tabs { display: flex; background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border); }
.tab {
  flex: 1; text-align: center; padding: 24rpx 0; font-size: 28rpx;
  color: var(--c-text-second); position: relative;
}
.tab.active { color: var(--c-ink); font-weight: 700; }
.tab.active::after {
  content: ''; position: absolute; left: 30%; right: 30%; bottom: 0;
  height: 4rpx; background: var(--c-primary);
}
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.content { flex: 1; padding: 24rpx; }
.md { font-size: 28rpx; line-height: 1.7; color: var(--c-text-body); white-space: pre-wrap; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/src/pages/curriculum/unit-detail.vue frontend/miniprogram/src/pages/curriculum/kp-content.vue
git commit -m "feat(m2): add unit detail + KP content pages"
```

---

## Task 8: 个人中心学期卡接入 units 入口

**Files:**
- Modify: `frontend/miniprogram/src/pages/profile/index.vue:32-44`

- [ ] **Step 1: 把学期卡片改成可点击**

替换 profile/index.vue 中行 32-44 的 `<view v-if="mySemesters.length" class="sem-list">` 块：

```vue
      <view v-if="mySemesters.length" class="sem-list">
        <view
          v-for="s in mySemesters"
          :key="s.id"
          class="sem-item"
          @tap="goUnits(s)"
        >
          <view class="sem-info">
            <text class="sem-name">{{ s.textbook_version }} {{ s.grade }} {{ s.semester }}</text>
            <text class="sem-tier" :class="`tier-${s.tier}`">{{ tierLabel(s.tier) }}</text>
          </view>
          <view class="sem-right">
            <text class="sem-expires">至 {{ s.expires_at.slice(0, 10) }}</text>
            <text class="chevron">›</text>
          </view>
        </view>
      </view>
      <view v-else>
        <text class="empty-tip">尚未购买任何学期</text>
        <button class="btn-secondary" style="margin-top:16rpx" @tap="goPreviewUnits">免费试读第 1 单元</button>
      </view>
```

- [ ] **Step 2: 加跳转函数到 `<script setup>` 末尾**

```typescript
function goUnits(s: { textbook_version: string; grade: string; semester: string }) {
  const url = `/pages/curriculum/units?textbook=${encodeURIComponent(s.textbook_version)}&grade=${encodeURIComponent(s.grade)}&semester=${encodeURIComponent(s.semester)}`
  uni.navigateTo({ url })
}
function goPreviewUnits() {
  // 引导未购用户先看免费的第 1 单元（用用户的 preferred_* 偏好；缺省走小学5上）
  const t = auth.user?.preferred_textbook_version || '译林版'
  const g = auth.user?.preferred_grade || '小学5年级'
  const sem = auth.user?.preferred_semester || '上'
  const url = `/pages/curriculum/units?textbook=${encodeURIComponent(t)}&grade=${encodeURIComponent(g)}&semester=${encodeURIComponent(sem)}`
  uni.navigateTo({ url })
}
```

- [ ] **Step 3: 加 chevron 样式到 `<style scoped>` 末尾**

```css
.sem-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4rpx; }
.chevron { color: var(--c-text-hint); font-size: 28rpx; }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/miniprogram/src/pages/profile/index.vue
git commit -m "feat(m2): wire profile semester card to curriculum units page"
```

---

## Task 9: Pilot 真实 AI 生成 1 个单元（人工质量验证）

**前提：** 用户提供真实 `DEEPSEEK_API_KEY` 写入 `backend/.env`（替换 `sk-placeholder-*`）。如果用户暂不提供，跳过此任务直接进 Task 10 跑 dev mock 全套，留 D-081 归档时说明真实生成需用户操作。

- [ ] **Step 1: 确认 .env 配置**

Run: `grep DEEPSEEK_API_KEY /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend/.env`
Expected: `DEEPSEEK_API_KEY=sk-...`（非 placeholder）

如显示 placeholder，停止此 Task 并告知用户：`需要用户提供 DEEPSEEK_API_KEY 才能跑 pilot。继续 Task 10？`

- [ ] **Step 2: 清掉先前 mock 生成的 U1**

Run:
```bash
docker exec -i enggramer-pg-dev psql -U postgres -d enggramer <<'EOF'
DELETE FROM knowledge_point_contents
  WHERE knowledge_point_id IN (
    SELECT kp.id FROM knowledge_points kp
    JOIN unit_knowledge_points ukp ON ukp.knowledge_point_id = kp.id
    JOIN curriculum_units u ON u.id = ukp.unit_id
    WHERE u.textbook_version='译林版' AND u.grade='小学5年级' AND u.semester='上' AND u.unit_no=1
  );
DELETE FROM unit_knowledge_points WHERE unit_id IN (
  SELECT id FROM curriculum_units
  WHERE textbook_version='译林版' AND grade='小学5年级' AND semester='上' AND unit_no=1
);
DELETE FROM curriculum_words WHERE unit_id IN (
  SELECT id FROM curriculum_units
  WHERE textbook_version='译林版' AND grade='小学5年级' AND semester='上' AND unit_no=1
);
DELETE FROM curriculum_units
  WHERE textbook_version='译林版' AND grade='小学5年级' AND semester='上' AND unit_no=1;
-- 注意：knowledge_points 全局共享不删，避免影响其他单元
EOF
```

- [ ] **Step 3: 跑真实 AI 生成 1 个单元**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --unit 1`
Expected: 输出 `[gen]  译林版 小学5年级 上 U1 … ✓ N KP, M 词`（N≥3, M≥5），耗时 15-60 秒

- [ ] **Step 4: 人工验证内容质量**

Run:
```bash
docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "
SELECT u.unit_title, kp.name, kp.category, length(kpc.content_md) AS md_len, kpc.dimension
FROM curriculum_units u
JOIN unit_knowledge_points ukp ON ukp.unit_id = u.id
JOIN knowledge_points kp ON kp.id = ukp.knowledge_point_id
JOIN knowledge_point_contents kpc ON kpc.knowledge_point_id = kp.id
WHERE u.textbook_version='译林版' AND u.grade='小学5年级' AND u.semester='上' AND u.unit_no=1
ORDER BY kp.code, kpc.dimension;"
```

Manual check：
- [ ] unit_title 是否符合教材真实标题（译林版小学5上 Unit 1 标题应类似 *Goldilocks and the three bears*）
- [ ] 每个 KP 的 4 维度 md_len 都 ≥ 100（确保不是空内容）
- [ ] knowledge_points.name 是否实际相关

如质量明显不合格，**停止 Task 10，回到 prompt 调优**（修 `_USER_PROMPT_TEMPLATE`），然后重跑 Step 2 + Step 3。

- [ ] **Step 5: Commit（如有 prompt 调整）**

```bash
git add backend/app/services/curriculum_ai_service.py
git commit -m "tune(m2): refine AI prompt based on pilot quality review"
```

如无调整跳过此 Step。

---

## Task 10: 全量 AI 生成 4 学期 + 真机验证

- [ ] **Step 1: 决策点 — 真实 API 还是 dev mock？**

如果 Task 9 真实生成质量合格 → 用真实 API 跑全量（耗时 5-15 分钟、成本约 $0.5-2）
如果用户暂未提供 key 或质量不达标 → 用 dev mock 跑全量（瞬时、零成本、内容是占位文本）

dev mock 跑全量：DEEPSEEK_API_KEY 仍是 `sk-placeholder-*`
真实跑全量：DEEPSEEK_API_KEY 是真实 key

- [ ] **Step 2: 跑全套**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && PYTHONPATH=backend python backend/scripts/seed_curriculum.py --all`
Expected:
- dev mock: 32 个单元全部 `[gen]` 或 `[skip]`，< 30 秒
- 真实 API: 5-15 分钟，每个单元 15-60 秒

- [ ] **Step 3: 行数核验**

Run: `docker exec enggramer-pg-dev psql -U postgres -d enggramer -c "SELECT textbook_version, grade, semester, count(*) AS units FROM curriculum_units GROUP BY 1,2,3 ORDER BY 1,2,3;"`
Expected: 4 行，每行 units=8

- [ ] **Step 4: 后端起服务**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend && uvicorn app.main:app --reload --port 8000`（后台或新 terminal）

Run health check: `curl -s http://localhost:8000/api/v1/health | head -1`
Expected: `{"code":200,...}`

- [ ] **Step 5: API 烟测**

Run: `curl -s "http://localhost:8000/api/v1/curriculum/units?textbook_version=%E8%AF%91%E6%9E%97%E7%89%88&grade=%E5%B0%8F%E5%AD%A65%E5%B9%B4%E7%BA%A7&semester=%E4%B8%8A" -H "Authorization: Bearer <用户 token>" | python -m json.tool | head -50`
Expected: 返回 8 个单元，u1.locked=false，u2-u8.locked=true（或全部 locked=false 如果用户已购该学期）

- [ ] **Step 6: 前端重新编译**

Run: `cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/frontend/miniprogram && npm run dev:mp-weixin`（后台跑）

- [ ] **Step 7: 真机验证（人工，5 分钟）**

在 WeChat DevTools：
- [ ] 个人中心 → 点学期卡片"译林版 小学5年级 上" → 跳到 units 列表 → 截图
- [ ] 列表显示 8 个单元，u1 无锁、u2-u8 有 🔒 → 截图
- [ ] 点 u1 → 进入详情页，显示知识点列表 + 词汇 → 截图
- [ ] 点任一知识点 → 进入 4 维度切换页，能切换 listening/dictation/grammar/writing → 截图
- [ ] 点 u2 → 弹出"需要解锁"modal → 截图

把 5 张截图发给我确认 M2 完成。

---

## Task 11: 归档 D-081 + Commit + Push

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 追加 D-081 决策**

在 `docs/决策归档.md` 末尾追加：

```markdown
## D-081｜2026-05-31｜V2 M2 教材内容 + 课程浏览 + 付费墙落地

**背景**：
M1（V2 数据模型 + 学期会员）已真机验证通过。M2 目标：让用户能真的浏览教材内容、付费墙生效。

**决策**：
1. 教材种子内容采用"AI 一次性生成 4 个学期"路径（D-079 ）；dev mock 模式输出占位结构便于前端开发、真实 API key 下输出实际可用内容。
2. 付费墙规则：每学期 unit_no=1 永远免费试读；其余单元需对应 (textbook, grade, semester) 已购 PurchasedSemester（任意 tier）。
3. M2 不做音频；音频留 M2.5。
4. 教材层级：textbook_version × grade × semester × unit_no × knowledge_point × 4 dim。复用 d4（5 张）+ d11（1 张）已有表结构，0 张新建。
5. AI 生成幂等：按 `knowledge_points.code` 全局唯一约束保证多次跑只 upsert 不重复。

**新增代码**：
- 后端 schemas: `app/schemas/curriculum.py`（AIGeneratedUnit + UnitOut/KnowledgePointOut/KPContentOut）
- 后端 services: `app/services/curriculum_ai_service.py`（DeepSeek + dev mock）+ `app/services/curriculum_service.py`（persist + paywall + read）
- 后端 API: `app/api/v1/curriculum.py`（GET /units / /units/{id} / /knowledge-points/{id}/contents）
- CLI: `backend/scripts/seed_curriculum.py`（支持 --unit / --units 1-N / --all 三种模式 + 断点续传）
- 前端 API: `frontend/miniprogram/src/api/curriculum.ts`
- 前端页面: `pages/curriculum/{units, unit-detail, kp-content}.vue`
- 前端入口: `pages/profile/index.vue` 学期卡 → tap 跳 units 页；空状态加"免费试读"按钮
- 测试: `tests/services/test_curriculum_{ai_service,service}.py` + `tests/api/test_curriculum.py`

**测试结果**：
- pytest 全套：（填实际数）/（填实际数）pass
- seed 全套（4 学期 × 8 单元 = 32 单元）执行：（dev mock / 真实 API）成功
- 真机：profile → units → unit-detail → kp-content + paywall modal 全链路 ✓

**为什么不做**：
- 音频（TTS + 跟读评测）：M2.5 单独迭代，避免 M2 翻倍工期
- 课程导航底部 tab：保持现有 4-tab 不动；从 profile 学期卡进入，符合"先购买后学习"心智，避免未付费用户误以为有大量免费课
- 真题录入（D-079 的 d12_v2_exams）：M3 才做，本 milestone 仅做"内容生产+消费链路"

**遗留**：
- prompt 调优持续：实际跑 4 学期 32 单元后会暴露质量短板，需要 D-081-续 或在 M2.5 做 batch 重生成
- 没有"unit_no=1 包含哪些 KP"的 ops 控制；目前 AI 决定（D-082 候选）

**相关**：D-079 V2 演进评估、D-080 V2 M1 数据模型 + 学期会员、Plan N → Plan O（M2）
```

- [ ] **Step 2: 提交归档**

```bash
git add docs/决策归档.md
git commit -m "docs(d-081): archive V2 M2 curriculum content + paywall decision"
```

- [ ] **Step 3: 全套测试 + push**

Run:
```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
PYTHONPATH=backend pytest -q  # 应全绿
git log --oneline -15  # 检查 M2 commit 链
git push origin HEAD
```

Expected: 全绿；远端 push 成功

- [ ] **Step 4: 通报完成**

向用户报告：
- M2 完整落地 commit 数（应为 11-13 个）
- 测试通过数
- 真机验证截图（来自 Task 10 Step 7）

---

## 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| AI 生成质量不达标 | 用户看到 mock 占位文本 | Task 9 pilot 验证质量；不合格则 prompt 调优重跑 |
| 真实 API key 未提供 | 全套只能跑 dev mock | seed 脚本支持 dev mock 全跑通，UI 可演示；标 D-081 待补 |
| persist_unit 并发跑同单元 | UniqueConstraint 冲突 | 单线程 seed 脚本无此问题；future ops 后台并发时加 advisory lock |
| 用户已购学期 = 上，浏览下学期被锁 | 符合设计（每学期独立） | 在 unit list 头部展示明确的 (textbook, grade, semester) 让用户知道在看哪个 |
| 已有 KP code 与本次生成冲突 | upsert 走更新分支，但 applicable_grades 数组未合并 | 现实中 4 个学期的 KP code 前缀不同（yl-g5s1 vs yl-g5s2 vs yl-g7s1...），不会冲突；future 跨学期共享 KP 时再处理 |

---

## Self-Review

**1. 规格覆盖**
- ✅ AI 生成 4 学期：Task 4 (--all) + Task 10
- ✅ 译林版小学5上下 + 初中7上下：seed 脚本 `FULL_SEMESTERS` 常量
- ✅ 前端课程浏览：Task 6/7/8（3 个页面 + 入口接入）
- ✅ 前 1 单元免费付费墙：is_unit_locked() unit_no==1 短路 + Task 2/3 测试覆盖
- ✅ 复用 d4/d11 表结构：persist_unit 写 6 张表，未建任何新表
- ✅ M2 不做音频：所有页面、schema、prompt 都不涉及音频生成

**2. 占位符检查**
- 无 "TBD/TODO/implement later"
- 所有代码 step 都贴出完整代码
- 命令都给出 Expected
- Task 9 的"用户未提供 key 则跳过"是显式分支不是占位

**3. 类型一致性**
- `AIGeneratedUnit / AIKnowledgePointItem / AIWordItem` 字段在 Task 0 定义，Task 1 mock + Task 2 persist 都对齐
- `UnitOut / UnitDetailOut / KnowledgePointOut / WordOut / KPContentOut` 后端 schemas（Task 0）↔ 前端 types（Task 5）字段一致
- `is_unit_locked(textbook_version, grade, semester, unit_no)` 签名在 Task 2 定义，Task 3 read 函数引用一致
- `semester_service.query_access` 已有，无需新建

---
