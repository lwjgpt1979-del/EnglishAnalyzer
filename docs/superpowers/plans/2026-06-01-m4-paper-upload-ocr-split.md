# M4 整卷上传 OCR 拆题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学生上传整张英语试卷（多页图片）→ 后台 OCR 识别 → DeepSeek 自动拆分成多道结构化题目 → 落库到 `user_uploaded_papers` + `user_paper_questions`，前端可查看每题题干/学生作答/正确答案/对错。

**Architecture:** 复用现有 OCR 管线（`ocr_service.run_ocr` 双引擎 + dev mock，`upload_service` 预签名）。新增一个「整卷拆题」解析服务（`paper_split_service`，DeepSeek 把整卷 OCR 文字拆成题目数组，dev mock 确定性返回 2 题）。新增 `user_paper_service` 编排「建卷→后台跑 OCR→拆题→落库」，沿用 `ocr.py` 已验证的 `BackgroundTasks + async_session_factory` 模式。新增 `user_papers.py` 路由。**M4 表已由 M1 在 migration 0007 建好，本计划不需要新迁移。**

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL + DeepSeek（openai SDK，dev mock 兜底）。

---

## 关键约定（执行前必读）

- **测试运行方式**：`cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/...`（测试在 repo 根 `tests/`，不在 backend/ 下）。
- **dev mock 检测**：DeepSeek key 以 `sk-placeholder` 开头即 dev 模式（见 `ocr_parser_service._is_deepseek_dev_mode`）。OCR 引擎以 `placeholder` 开头即 dev（见 `ocr_service`）。测试有 `force_dev_mode` autouse fixture 强制 `settings.deepseek_api_key = "sk-placeholder-for-test"`，故测试默认走 dev mock。
- **httpx ASGITransport 会 inline await BackgroundTasks**：API 测试里 POST 创建试卷返回时，后台 OCR 管线**已经跑完**，可直接断言 `ocr_status == "completed"`。
- **`question_type` 合法值**（`ai_question_type_enum`）：`单选 / 填空 / 完型 / 阅读 / 写作 / 判断 / 连线`。拆题服务输出必须落在这 7 个值内，非法值归一化为 `单选`（最常见）。
- **service 测试** 用每文件本地 `db_session` fixture（`_async_session_factory()` + teardown `await s.rollback()`）。**API 测试** 用 `client` fixture（httpx `AsyncClient` + `ASGITransport(app=app)`）。参照 `tests/services/test_question_service.py` 与 `tests/api/test_questions.py` 现有写法。
- dev-mock OCR 文字（`ocr_service._MOCK_PRINTED` / `_MOCK_HANDWRITTEN`）天然含 2 道题（27、28），是拆题的确定性测试夹具。

## File Structure

- Create: `backend/app/schemas/user_papers.py` — 整卷上传相关 Pydantic schemas
- Create: `backend/app/services/paper_split_service.py` — DeepSeek 整卷拆题 + dev mock
- Create: `backend/app/services/user_paper_service.py` — 建卷 / 列表 / 详情 / 后台 OCR 管线编排
- Create: `backend/app/api/v1/user_papers.py` — 路由（POST 建卷 / GET 列表 / GET 详情）
- Modify: `backend/app/api/v1/router.py` — 注册 user_papers_router
- Test: `tests/services/test_paper_split_service.py`
- Test: `tests/services/test_user_paper_service.py`
- Test: `tests/api/test_user_papers.py`

---

### Task 0: 整卷上传 Schemas

**Files:**
- Create: `backend/app/schemas/user_papers.py`

- [ ] **Step 1: 写 schemas（无测试，纯数据类，下游 task 会用到）**

```python
"""V2 整卷上传 OCR 拆题 Pydantic schemas（D-089 / M4）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserPaperCreate(BaseModel):
    """学生提交整卷：一张或多张试卷图片 URL（已通过 upload 预签名上传到 COS）。"""
    source_image_urls: list[str] = Field(..., min_length=1, max_length=20)
    title: str | None = Field(None, max_length=100)


class UserPaperQuestionOut(BaseModel):
    """拆出来的单题。"""
    id: uuid.UUID
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None
    is_wrong: bool


class UserPaperOut(BaseModel):
    """试卷概要（列表用）。"""
    id: uuid.UUID
    title: str | None
    source_image_urls: list[str]
    ocr_status: str | None
    question_count: int
    created_at: datetime


class UserPaperDetailOut(UserPaperOut):
    """试卷详情：概要 + 拆出的题目列表。"""
    questions: list[UserPaperQuestionOut]


class UserPaperListOut(BaseModel):
    items: list[UserPaperOut]
    total: int
```

- [ ] **Step 2: 确认能 import（语法自检）**

Run: `cd backend && python -c "from app.schemas.user_papers import UserPaperCreate, UserPaperDetailOut, UserPaperListOut; print('ok')"`
Expected: 打印 `ok`，无 ImportError。

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/user_papers.py
git commit -m "feat(m4): 整卷上传 OCR 拆题 Pydantic schemas"
```

---

### Task 1: 整卷拆题 Service（DeepSeek 多题拆分 + dev mock）

**Files:**
- Create: `backend/app/services/paper_split_service.py`
- Test: `tests/services/test_paper_split_service.py`

- [ ] **Step 1: 写失败测试**

```python
"""整卷拆题服务测试（D-089 / M4）。dev mock 确定性返回 2 题。"""
from __future__ import annotations

import pytest

from app.services.ocr_service import OcrResult, _MOCK_PRINTED, _MOCK_HANDWRITTEN
from app.services.paper_split_service import split_paper_questions, ParsedPaperQuestion


@pytest.mark.asyncio
async def test_split_dev_mock_returns_two_questions():
    """force_dev_mode autouse → DeepSeek dev mock：从 _MOCK_PRINTED/_MOCK_HANDWRITTEN 拆出 2 题。"""
    ocr = OcrResult(printed_text=_MOCK_PRINTED, handwritten_text=_MOCK_HANDWRITTEN)
    questions = await split_paper_questions(ocr)

    assert isinstance(questions, list)
    assert len(questions) == 2
    assert all(isinstance(q, ParsedPaperQuestion) for q in questions)

    q27, q28 = questions
    assert q27.question_no == "27"
    assert q27.question_type == "单选"
    assert q27.student_answer == "B"
    assert q27.stem and "hand in" in q27.stem

    assert q28.question_no == "28"
    assert q28.student_answer == "B"


@pytest.mark.asyncio
async def test_split_empty_ocr_returns_empty_list():
    """两路 OCR 都为空 → 返回空列表，不报错。"""
    ocr = OcrResult(printed_text="", handwritten_text="")
    questions = await split_paper_questions(ocr)
    assert questions == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_paper_split_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.paper_split_service'`。

- [ ] **Step 3: 实现拆题服务**

```python
"""整卷拆题：将整卷 OCR 原始文字（印刷体 + 手写体）送入 DeepSeek，拆分为多道结构化题目。

输入：OcrResult（印刷体 = 题目，手写体 = 学生作答）
输出：list[ParsedPaperQuestion]，每题含 question_no / question_type / stem /
      student_answer / correct_answer / explanation。

Dev 模式（deepseek_api_key 以 'sk-placeholder' 开头）跳过真实 API，确定性返回 2 题，
让整条链路在无账号时可完整测试。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.ocr_service import OcrResult

# 与 ai_question_type_enum 对齐
_VALID_TYPES = {"单选", "填空", "完型", "阅读", "写作", "判断", "连线"}


@dataclass
class ParsedPaperQuestion:
    """DeepSeek 从整卷 OCR 文字拆出的单题结构化字段。"""
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None


_SYSTEM_PROMPT = (
    "你是一个专业的英语试卷结构化助手。"
    "你会收到一整张英语试卷的 OCR 识别文字（印刷体为题目，手写体为学生作答），"
    "请把整卷拆分为一道道独立的题目，严格按 JSON 数组输出，不要任何额外文字。"
)

_USER_PROMPT_TEMPLATE = """以下是从一整张英语试卷图片中识别到的文字：

【印刷体识别（题目印刷文字，含题号/题干/选项）】
{printed_text}

【手写体识别（学生作答内容，通常是题号 + 答案）】
{handwritten_text}

请把整卷拆分为多道题目，返回纯 JSON 数组（不要任何 markdown 代码块或额外文字）。
数组每一项格式：
{{
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "student_answer": "该题学生手写答案（按题号从手写体匹配，无法识别则 null）",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}}

要求：按题号顺序输出；识别不到任何题目时返回空数组 []。"""


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _normalize_type(raw: object) -> str:
    """归一化题型到 ai_question_type_enum 合法值，非法值兜底为 单选。"""
    return raw if raw in _VALID_TYPES else "单选"


def _dev_mock_split(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """dev 模式确定性拆题：识别 _MOCK_PRINTED 里的两道题。

    OCR mock 文字结构固定（题号 27/28，每题题干一行 + 选项一行），
    手写体为 '27. B\\n28. B'。这里做轻量行解析，保证测试确定性，
    无需真实 DeepSeek。OCR 全空时返回 []。
    """
    if not (ocr.printed_text or "").strip():
        return []

    # 解析手写体答案：'27. B' -> {'27': 'B'}
    answers: dict[str, str] = {}
    for line in (ocr.handwritten_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # 形如 '27. B' 或 '27 B'
        parts = line.replace(".", " ").split()
        if len(parts) >= 2 and parts[0].isdigit():
            answers[parts[0]] = parts[1]

    # 解析印刷体题目：题号行开启一题，后续非题号行并入题干
    questions: list[ParsedPaperQuestion] = []
    cur_no: str | None = None
    cur_lines: list[str] = []

    def _flush() -> None:
        if cur_no is None:
            return
        stem = "\n".join(cur_lines).strip() or None
        questions.append(
            ParsedPaperQuestion(
                question_no=cur_no,
                question_type="单选",
                stem=stem,
                student_answer=answers.get(cur_no),
                correct_answer=None,
                explanation=None,
            )
        )

    for line in ocr.printed_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head = stripped.split(".", 1)[0]
        if head.isdigit():
            _flush()
            cur_no = head
            rest = stripped.split(".", 1)[1].strip() if "." in stripped else ""
            cur_lines = [rest] if rest else []
        else:
            cur_lines.append(stripped)
    _flush()
    return questions


async def split_paper_questions(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """将整卷 OCR 文字拆分为多道结构化题目。

    Dev 模式：确定性本地拆题，无需 API。
    Prod 模式：DeepSeek 拆题，返回 JSON 数组。

    异常处理：
    - API 错误 → AppError(502, "整卷拆题服务暂时不可用")
    - JSON 解析失败 / 非数组 → AppError(500, "整卷拆题返回格式异常")
    """
    if _is_deepseek_dev_mode():
        return _dev_mock_split(ocr)

    if not (ocr.printed_text or "").strip():
        return []

    prompt = _USER_PROMPT_TEMPLATE.format(
        printed_text=ocr.printed_text or "(无印刷体识别结果)",
        handwritten_text=ocr.handwritten_text or "(无手写体识别结果)",
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
        raise AppError(code=502, message=f"整卷拆题服务暂时不可用（{exc}）") from exc

    raw_text = (response.choices[0].message.content or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[-2] if raw_text.count("```") >= 2 else raw_text
        raw_text = raw_text.lstrip("json").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="整卷拆题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="整卷拆题返回格式异常")

    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
            )
        )
    return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_paper_split_service.py -v`
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_split_service.py tests/services/test_paper_split_service.py
git commit -m "feat(m4): 整卷拆题 service（DeepSeek 多题拆分 + dev mock）"
```

---

### Task 2: 整卷 Service（建卷 / 列表 / 详情 / 后台 OCR 管线）

**Files:**
- Create: `backend/app/services/user_paper_service.py`
- Test: `tests/services/test_user_paper_service.py`

- [ ] **Step 1: 写失败测试**

测试需要一个真实 user（FK `users.id`）。参照 `tests/services/test_question_service.py` 现有 `_make_user` 辅助；若该文件没有可复用的，本测试内自建。

```python
"""整卷 service 测试（D-089 / M4）：建卷 + 后台管线 + 详情。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory as _async_session_factory
from app.models.d1_users import User
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.services import user_paper_service


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _async_session_factory() as s:
        try:
            yield s
        finally:
            await s.rollback()


async def _make_user(s: AsyncSession) -> User:
    # User 模型字段名是 openid（非 wx_openid）；role 为 user_role_enum（"student"），
    # is_active 有 server_default=true 可省略。见 app/models/d1_users.py。
    u = User(
        id=uuid.uuid4(),
        openid=f"openid-{uuid.uuid4().hex[:8]}",
        role="student",
    )
    s.add(u)
    await s.commit()
    return u


@pytest.mark.asyncio
async def test_create_paper_sets_pending(db_session: AsyncSession):
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg", "https://mock/p2.jpg"],
        title="期中卷",
    )
    assert paper.id is not None
    assert paper.ocr_status == "pending"
    assert paper.title == "期中卷"
    assert len(paper.source_image_urls) == 2


@pytest.mark.asyncio
async def test_run_pipeline_populates_questions(db_session: AsyncSession):
    """dev mock：跑管线后 ocr_status=completed 且拆出 2 题。"""
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()

    await user_paper_service.run_paper_pipeline(paper.id)

    # 用新 session 读回（管线内部用独立 session 提交）
    async with _async_session_factory() as s:
        reloaded = await s.get(UserUploadedPaper, paper.id)
        assert reloaded.ocr_status == "completed"
        qs = (await s.execute(
            select(UserPaperQuestion).where(UserPaperQuestion.user_paper_id == paper.id)
        )).scalars().all()
        assert len(qs) == 2
        nos = sorted(q.question_no for q in qs)
        assert nos == ["27", "28"]
        assert all(q.student_answer == "B" for q in qs)


@pytest.mark.asyncio
async def test_get_paper_detail_returns_questions(db_session: AsyncSession):
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()
    await user_paper_service.run_paper_pipeline(paper.id)

    detail = await user_paper_service.get_paper_detail(
        db_session, paper_id=paper.id, student_id=user.id
    )
    assert detail is not None
    assert detail.question_count == 2
    assert len(detail.questions) == 2


@pytest.mark.asyncio
async def test_get_paper_detail_wrong_owner_returns_none(db_session: AsyncSession):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=owner.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()

    detail = await user_paper_service.get_paper_detail(
        db_session, paper_id=paper.id, student_id=other.id
    )
    assert detail is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_user_paper_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.user_paper_service'`（或 AttributeError）。

- [ ] **Step 3: 实现 service**

```python
"""整卷上传 service（D-089 / M4）：建卷 / 列表 / 详情 / 后台 OCR 拆题管线。

后台管线沿用 ocr.py 已验证的「BackgroundTasks + 独立 async_session_factory」模式：
管线内部开独立 session 提交，避免与请求 session 串扰。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.schemas.user_papers import (
    UserPaperDetailOut,
    UserPaperOut,
    UserPaperQuestionOut,
)


def _is_wrong(student_answer: str | None, correct_answer: str | None) -> bool:
    """学生答案与正确答案都存在且归一化后不同 → 判错；否则 False（无法判定不算错）。"""
    if not student_answer or not correct_answer:
        return False
    return student_answer.strip().lower() != correct_answer.strip().lower()


async def create_paper(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    source_image_urls: list[str],
    title: str | None,
) -> UserUploadedPaper:
    """创建整卷记录，ocr_status=pending（后台管线随后处理）。"""
    paper = UserUploadedPaper(
        student_id=student_id,
        title=title,
        source_image_urls=source_image_urls,
        ocr_status="pending",
    )
    db.add(paper)
    await db.flush()
    await db.refresh(paper)
    return paper


async def run_paper_pipeline(paper_id: uuid.UUID) -> None:
    """后台任务：对整卷每张图跑 OCR → 合并文字 → DeepSeek 拆题 → 落库题目。

    用独立 session（async_session_factory），与触发请求的 session 解耦。
    """
    from app.core.database import async_session_factory as _async_session_factory
    from app.services.ocr_service import OcrResult, run_ocr
    from app.services.paper_split_service import split_paper_questions

    async with _async_session_factory() as db:
        paper: UserUploadedPaper | None = await db.get(UserUploadedPaper, paper_id)
        if paper is None:
            return

        paper.ocr_status = "processing"
        await db.commit()

        try:
            # 逐张 OCR，合并印刷体/手写体文字
            printed_parts: list[str] = []
            handwritten_parts: list[str] = []
            for url in paper.source_image_urls:
                ocr = await run_ocr(url)
                if ocr.printed_text:
                    printed_parts.append(ocr.printed_text)
                if ocr.handwritten_text:
                    handwritten_parts.append(ocr.handwritten_text)

            merged = OcrResult(
                printed_text="\n".join(printed_parts),
                handwritten_text="\n".join(handwritten_parts),
            )
            parsed = await split_paper_questions(merged)

            for pq in parsed:
                db.add(
                    UserPaperQuestion(
                        user_paper_id=paper.id,
                        question_no=pq.question_no,
                        question_type=pq.question_type,
                        stem=pq.stem,
                        student_answer=pq.student_answer,
                        correct_answer=pq.correct_answer,
                        explanation=pq.explanation,
                        is_wrong=_is_wrong(pq.student_answer, pq.correct_answer),
                    )
                )
            paper.ocr_status = "completed"
        except Exception:
            paper.ocr_status = "failed"

        await db.commit()


async def _question_count(db: AsyncSession, paper_id: uuid.UUID) -> int:
    return int(
        (await db.execute(
            select(func.count(UserPaperQuestion.id)).where(
                UserPaperQuestion.user_paper_id == paper_id
            )
        )).scalar_one()
    )


async def list_papers(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50
) -> list[UserPaperOut]:
    """列出某学生的全部整卷（倒序），含每卷题目数。"""
    rows = (await db.execute(
        select(UserUploadedPaper)
        .where(UserUploadedPaper.student_id == student_id)
        .order_by(UserUploadedPaper.created_at.desc())
        .limit(limit)
    )).scalars().all()

    out: list[UserPaperOut] = []
    for p in rows:
        out.append(
            UserPaperOut(
                id=p.id,
                title=p.title,
                source_image_urls=list(p.source_image_urls or []),
                ocr_status=p.ocr_status,
                question_count=await _question_count(db, p.id),
                created_at=p.created_at,
            )
        )
    return out


async def get_paper_detail(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> UserPaperDetailOut | None:
    """整卷详情（含题目列表）。非本人持有 → None。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    qs = (await db.execute(
        select(UserPaperQuestion)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .order_by(UserPaperQuestion.created_at.asc())
    )).scalars().all()

    questions = [
        UserPaperQuestionOut(
            id=q.id,
            question_no=q.question_no,
            question_type=q.question_type,
            stem=q.stem,
            student_answer=q.student_answer,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
            is_wrong=q.is_wrong,
        )
        for q in qs
    ]

    return UserPaperDetailOut(
        id=paper.id,
        title=paper.title,
        source_image_urls=list(paper.source_image_urls or []),
        ocr_status=paper.ocr_status,
        question_count=len(questions),
        created_at=paper.created_at,
        questions=questions,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_user_paper_service.py -v`
Expected: 4 passed。

> 注意：若 `_make_user` 的 `User` 必填字段与实际模型不符（如缺 `nickname`），按 `app/models/d1_users.py` 真实定义补齐，参照 `tests/services/test_question_service.py` 里已有的建 user 方式。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/user_paper_service.py tests/services/test_user_paper_service.py
git commit -m "feat(m4): 整卷 service（建卷/列表/详情/后台 OCR 拆题管线）"
```

---

### Task 3: 整卷 API 路由 + 注册

**Files:**
- Create: `backend/app/api/v1/user_papers.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `tests/api/test_user_papers.py`

- [ ] **Step 1: 写失败测试**

`client` fixture 由 `tests/api/conftest.py` 全局提供（httpx `AsyncClient` + `ASGITransport(app=app)`），无需重定义。鉴权沿用 `tests/api/test_questions.py` 已验证的本文件内 `_login` 辅助：patch `app.services.auth_service.wechat_code2session` 返回固定 openid → POST `/api/v1/auth/wx-login` 拿 token（登录流程会 upsert 出一个真实 user，故 API 测试无需手动建 User）。`force_dev_mode` autouse fixture 也按 test_questions.py 同款写在本文件内。

```python
"""整卷上传 API 测试（D-089 / M4）。httpx ASGITransport 会 inline await 后台任务，
故 POST 返回时 OCR 管线已跑完，可直接断言 completed + 2 题。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"m4_paper_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_create_paper_runs_pipeline(client):
    headers = await _login(client, "create")
    resp = await client.post(
        "/api/v1/user-papers",
        headers=headers,
        json={"source_image_urls": ["https://mock/p1.jpg"], "title": "期中卷"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    paper_id = data["id"]
    assert data["title"] == "期中卷"

    # 后台管线已 inline 跑完
    detail = await client.get(f"/api/v1/user-papers/{paper_id}", headers=headers)
    assert detail.status_code == 200
    d = detail.json()["data"]
    assert d["ocr_status"] == "completed"
    assert d["question_count"] == 2
    assert len(d["questions"]) == 2


@pytest.mark.asyncio
async def test_list_papers(client):
    headers = await _login(client, "list")
    await client.post(
        "/api/v1/user-papers",
        headers=headers,
        json={"source_image_urls": ["https://mock/p1.jpg"]},
    )
    resp = await client.get("/api/v1/user-papers", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] >= 1
    assert any(it["question_count"] == 2 for it in body["items"])


@pytest.mark.asyncio
async def test_get_paper_not_found(client):
    headers = await _login(client, "notfound")
    resp = await client.get(f"/api/v1/user-papers/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
```

> **重要**：上面 `_login` 与 `force_dev_mode` 直接照搬 `tests/api/test_questions.py` 的写法（已验证可用）。`/api/v1/auth/wx-login` 的返回结构是 `{"data": {"access_token": ...}}`。若 auth_service 的 mock 目标函数名有出入，以 test_questions.py 当前实际为准。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/api/test_user_papers.py -v`
Expected: FAIL（路由 404 / 模块不存在）。

- [ ] **Step 3: 实现路由**

```python
"""整卷上传 OCR 拆题 API（D-089 / M4）。

POST /user-papers          建卷 + 触发后台 OCR 拆题管线
GET  /user-papers          列出本人整卷
GET  /user-papers/{id}     整卷详情（含拆出的题目）
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.user_papers import UserPaperCreate, UserPaperListOut
from app.services import user_paper_service

router = APIRouter(prefix="/user-papers", tags=["user-papers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("")
async def create_user_paper(
    body: UserPaperCreate,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """建卷并异步触发 OCR 拆题。"""
    paper = await user_paper_service.create_paper(
        db,
        student_id=current_user.id,
        source_image_urls=body.source_image_urls,
        title=body.title,
    )
    await db.commit()

    background_tasks.add_task(user_paper_service.run_paper_pipeline, paper.id)

    return make_ok(
        {
            "id": str(paper.id),
            "title": paper.title,
            "ocr_status": paper.ocr_status,
        }
    )


@router.get("")
async def list_user_papers(
    db: DbDep,
    current_user: UserDep,
):
    """列出本人整卷。"""
    items = await user_paper_service.list_papers(db, student_id=current_user.id)
    out = UserPaperListOut(items=items, total=len(items))
    return make_ok(out.model_dump(mode="json"))


@router.get("/{paper_id}")
async def get_user_paper(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """整卷详情（含题目）。"""
    detail = await user_paper_service.get_paper_detail(
        db, paper_id=paper_id, student_id=current_user.id
    )
    if detail is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(detail.model_dump(mode="json"))
```

- [ ] **Step 4: 注册路由**

修改 `backend/app/api/v1/router.py`：在 import 区加一行，在 include 区加一行。

import 区（紧跟 `from app.api.v1.questions import router as questions_router` 之后）：
```python
from app.api.v1.user_papers import router as user_papers_router
```

include 区（紧跟 `v1_router.include_router(questions_router)` 之后）：
```python
v1_router.include_router(user_papers_router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/api/test_user_papers.py -v`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/user_papers.py backend/app/api/v1/router.py tests/api/test_user_papers.py
git commit -m "feat(m4): 整卷上传 OCR 拆题 API（建卷/列表/详情）+ 路由注册"
```

---

### Task 4: 全量验证 + D-089 归档 + push

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 跑全量后端测试**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests -q`
Expected: 全绿（M4 新增约 9 个测试，之前 ~279 passed 之上递增）。若有偶发 flaky，重跑确认稳定。

- [ ] **Step 2: 归档 D-089（顶部插入，降序）**

在 `docs/决策归档.md` 最顶部插入（格式与 D-088 一致：日期 / 背景 / 结论 / 未做 / 影响范围 / 相关 / 提交链）：

```markdown
## D-089 整卷上传 OCR 拆题（M4）

- **日期**：2026-06-01
- **背景**：M1/M2/M3 已完成，内容批量预生成需真实 DeepSeek key 暂缓。优先做纯代码、不花钱的 M4——学生上传整张试卷，自动 OCR + 拆题落库，补齐核心功能闭环。
- **结论**：复用既有 OCR 双引擎 + dev mock 管线，新增 `paper_split_service`（DeepSeek 整卷拆多题，dev mock 确定性返回 2 题）、`user_paper_service`（建卷/列表/详情 + 后台 OCR 拆题管线）、`user_papers.py` 路由（POST 建卷 / GET 列表 / GET 详情）。落库到 M1 已建的 `user_uploaded_papers` + `user_paper_questions`，无需新迁移。`is_wrong` 由「学生答案 vs 正确答案归一化比较」推断。
- **未做**：① 真实 DeepSeek 拆题质量未验证（dev mock 兜底，需 key 后实测）；② `matched_exam_question_id` 暂不匹配题库（留待后续）；③ 前端整卷上传页未做（仅后端 API）；④ 知识点关联表 `user_paper_question_knowledge_points` 暂未写入。
- **影响范围**：backend services / api / schemas / tests；新增 3 个文件 + 路由注册；无 DB 迁移；不花钱。
- **相关**：D-079（V2 演进）、D-068（OCR 双引擎）、M1 表骨架。
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-089 整卷上传 OCR 拆题（M4）"
git push origin main
```

---

## Self-Review（已核对）

- **Spec 覆盖**：建卷 / 后台 OCR / DeepSeek 拆多题 / 落库 user_paper_questions / 列表 / 详情 — 均有 task 覆盖。
- **类型一致**：`ParsedPaperQuestion`（Task 1 定义）→ Task 2 消费字段名一致（question_no/question_type/stem/student_answer/correct_answer/explanation）；`UserPaperOut`/`UserPaperDetailOut`（Task 0）→ Task 2 service 返回、Task 3 路由 `.model_dump(mode="json")` 一致。
- **题型合法值**：拆题 `_normalize_type` 兜底到 `ai_question_type_enum` 7 值之内，避免 enum 写库报错。
- **无新迁移**：M4 表在 0007 已建，已确认。
- **Placeholder 扫描**：每个写代码的 step 都给了完整代码；测试鉴权/建 user 处明确提示「按 test_questions.py / d1_users.py 真实写法适配」而非留空。
```
