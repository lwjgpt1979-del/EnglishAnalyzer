# M5 仿真题审核发布流（运营 admin API）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 把 AI 生成的仿真题从"自动发布"改为"先进草稿、运营审核后才发布"，并补齐运营 admin API（待审列表 + 逐题审核通过/驳回），让运营能在题目对学生可见前把关质量。

**Architecture:** 纯后端，零新前端栈，零 DB 迁移（`simulated_questions.status` enum `draft/reviewing/published/retired` 已存在；学生端 `list_questions_by_kp` 已只查 `published`）。改 `question_service.persist_questions` 默认写 `draft` 并加 `status` 参数；新增 service 审核读写函数；在既有 `api/v1/admin.py`（已有 `require_role("platform_admin")` 骨架）加两个端点。受影响的"依赖题目立即可见"的 seed 脚本与测试显式传 `status="published"`。

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic v2；pytest（httpx AsyncClient）。

---

### Task 1: persist_questions 默认改草稿 + 修复受影响调用方

**Files:**
- Modify: `backend/app/services/question_service.py:47-81`
- Modify: `backend/scripts/seed_questions.py`（persist 调用处显式传 `status="published"`）
- Modify: `tests/api/test_questions.py:60`（`_seed` helper persist 传 `status="published"`）
- Modify: `tests/services/test_question_service.py`（`test_list_filters_by_dimension` 等"persist 后调 list_questions_by_kp"的用例 persist 传 `status="published"`）
- Test: `tests/services/test_question_service.py`

**背景：** `persist_questions` 当前硬编码 `status="published"`（行 76），AI 题直接对学生可见。学生端 `list_questions_by_kp`（行 86-97）已只返回 `published`，所以只需让新题默认进 `draft`，出口闸门已就位。

- [ ] **Step 1: 写失败测试** —— 新增 `tests/services/test_question_service.py::test_persist_defaults_to_draft`

```python
@pytest.mark.asyncio
async def test_persist_defaults_to_draft(db_session, seeded_kp):
    """不传 status 时，新题默认进 draft（审核闸门）。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=3,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    assert all(str(r.status) == "draft" for r in created)


@pytest.mark.asyncio
async def test_persist_accepts_explicit_status(db_session, seeded_kp):
    """显式传 status='published' 时直接发布（seed/可信内容用）。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=2,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs, status="published",
    )
    await db_session.flush()
    assert all(str(r.status) == "published" for r in created)
```

- [ ] **Step 2: 跑测试确认失败**

Run（cwd = 仓库根；本项目 cwd 常在 `backend/`，则用 `cd ..` 后再跑）：
`cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer && python -m pytest tests/services/test_question_service.py::test_persist_defaults_to_draft -v`
Expected: FAIL —— 现在默认 published，断言 draft 失败。

- [ ] **Step 3: 实现** —— `persist_questions` 加 `status` 参数

```python
async def persist_questions(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    questions: list[AIGeneratedQuestion],
    dimension: str | None = None,
    status: str = "draft",          # 默认进草稿，需运营审核（M5）
) -> list[SimulatedQuestion]:
    """按 (kp_id, stem) 幂等 upsert。dimension 写入新行。status 默认 draft。"""
    out: list[SimulatedQuestion] = []
    for q in questions:
        existing = (await db.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp_id,
                SimulatedQuestion.stem == q.stem,
            )
        )).scalar_one_or_none()
        if existing is not None:
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
            dimension=dimension,
            status=status,
        )
        db.add(sq)
        await db.flush()
        out.append(sq)
    return out
```

- [ ] **Step 4: 修复受影响调用方**（让"依赖题目立即可见"的地方显式发布）
  - `backend/scripts/seed_questions.py`：所有 `persist_questions(...)` 调用补 `status="published"`（dev seed 是可信内容，直接发布）。
  - `tests/api/test_questions.py` 的 `_seed` helper（约行 60）：`persist_questions(s, kp_id=kp.id, questions=qs, status="published")`。
  - `tests/services/test_question_service.py::test_list_filters_by_dimension`（两处 persist）：补 `status="published"`。
  - 其余仅断言"行数/幂等/dimension"、不调 `list_questions_by_kp` 的 persist 测试不用改。

- [ ] **Step 5: 跑相关测试确认通过**

Run: `python -m pytest tests/services/test_question_service.py tests/api/test_questions.py -v`
Expected: 全 PASS（新增 2 例 + 原有用例）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/question_service.py backend/scripts/seed_questions.py tests/services/test_question_service.py tests/api/test_questions.py
git commit -m "feat(backend): 仿真题 persist 默认进草稿（审核闸门），seed/测试显式发布"
```

### Task 2: Service —— 待审列表 + 逐题审核

**Files:**
- Modify: `backend/app/services/question_service.py`
- Test: `tests/services/test_question_service.py`

新增两个 service 函数（放在 `list_questions_by_kp` 之后）：

```python
_REVIEWABLE_STATUSES = {"draft", "reviewing", "published", "retired"}


async def list_questions_for_review(
    db: AsyncSession,
    *,
    status: str = "draft",
    kp_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[SimulatedQuestion], int]:
    """运营按状态分页查仿真题（返回完整 ORM 行，含 answer，仅运营可见）。"""
    base = select(SimulatedQuestion).where(SimulatedQuestion.status == status)
    if kp_id is not None:
        base = base.where(SimulatedQuestion.knowledge_point_id == kp_id)
    total: int = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(SimulatedQuestion.created_at).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def review_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
    approve: bool,
) -> SimulatedQuestion:
    """审核一道题：approve→published，reject→retired。题不存在抛 AppError(404)。"""
    sq = (await db.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.id == question_id)
    )).scalar_one_or_none()
    if sq is None:
        from app.core.errors import AppError
        raise AppError(code=404, message="题目不存在")
    sq.status = "published" if approve else "retired"
    await db.flush()
    return sq
```

> 注：确认 `func` 已在文件顶部 `from sqlalchemy import select, func` 导入；若只导了 `select`，补 `func`。`AppError` 的真实路径以仓库现有用法为准（搜 `raise AppError` 或 `from app.` 确认模块），按现有约定调用。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_list_for_review_filters_status(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=3,
    )
    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)  # draft
    await db_session.flush()
    rows, total = await question_service.list_questions_for_review(
        db_session, status="draft", kp_id=seeded_kp.id,
    )
    assert total == 3 and len(rows) == 3
    rows_pub, total_pub = await question_service.list_questions_for_review(
        db_session, status="published", kp_id=seeded_kp.id,
    )
    assert total_pub == 0


@pytest.mark.asyncio
async def test_review_approve_publishes(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=1,
    )
    [sq] = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    reviewed = await question_service.review_question(
        db_session, question_id=sq.id, approve=True,
    )
    assert str(reviewed.status) == "published"


@pytest.mark.asyncio
async def test_review_reject_retires(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=1,
    )
    [sq] = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    reviewed = await question_service.review_question(
        db_session, question_id=sq.id, approve=False,
    )
    assert str(reviewed.status) == "retired"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/services/test_question_service.py -k "for_review or review_" -v`
Expected: FAIL（函数未定义）。

- [ ] **Step 3: 实现**（上面两个函数）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/services/test_question_service.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/question_service.py tests/services/test_question_service.py
git commit -m "feat(backend): 仿真题审核 service（待审列表 + 逐题通过/驳回）"
```

### Task 3: Schemas + Admin API 端点

**Files:**
- Modify: `backend/app/schemas/questions.py`（加运营审核 DTO）
- Modify: `backend/app/api/v1/admin.py`（加两个端点）
- Test: `tests/api/test_admin_questions.py`（新建）

新增 schema（`schemas/questions.py` 末尾）：

```python
# ─── 运营审核（M5）：运营可见完整字段（含 answer）────────────────────────────

class AdminQuestionItem(BaseModel):
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    question_type: str
    stem: str
    options: list[str] | None = None
    answer: str
    explanation: str | None = None
    difficulty: int
    dimension: str | None = None
    status: str


class AdminQuestionListOut(BaseModel):
    total: int
    items: list[AdminQuestionItem]


class QuestionReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")
```

新增端点（`api/v1/admin.py`）：

```python
import uuid as _uuid  # 若文件已 import uuid 则复用
from app.schemas.questions import (
    AdminQuestionItem, AdminQuestionListOut, QuestionReviewRequest,
)
from app.services import question_service


@router.get("/questions", response_model=BaseResponse[AdminQuestionListOut])
async def list_questions_for_review(
    db: DbDep,
    admin: AdminDep,
    status: str = "draft",
    kp_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
):
    rows, total = await question_service.list_questions_for_review(
        db, status=status, kp_id=kp_id, skip=skip, limit=limit,
    )
    items = [
        AdminQuestionItem(
            id=r.id,
            knowledge_point_id=r.knowledge_point_id,
            question_type=str(r.question_type),
            stem=r.stem,
            options=r.options,
            answer=r.answer,
            explanation=r.explanation,
            difficulty=r.difficulty,
            dimension=str(r.dimension) if r.dimension is not None else None,
            status=str(r.status),
        )
        for r in rows
    ]
    return make_ok(AdminQuestionListOut(total=total, items=items))


@router.post("/questions/{question_id}/review", response_model=BaseResponse[AdminQuestionItem])
async def review_question(
    question_id: uuid.UUID,
    body: QuestionReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    r = await question_service.review_question(
        db, question_id=question_id, approve=body.approve,
    )
    await db.commit()
    return make_ok(AdminQuestionItem(
        id=r.id, knowledge_point_id=r.knowledge_point_id,
        question_type=str(r.question_type), stem=r.stem, options=r.options,
        answer=r.answer, explanation=r.explanation, difficulty=r.difficulty,
        dimension=str(r.dimension) if r.dimension is not None else None,
        status=str(r.status),
    ))
```

- [ ] **Step 1: 写失败测试** —— `tests/api/test_admin_questions.py`

参考 `tests/api/test_teacher_p0.py::test_admin_review_certifies_teacher` 的 admin 鉴权套路（登录普通用户 → DB 把 `role` 改 `platform_admin` → 用其 token）。最小用例：

```python
import uuid
import pytest
from sqlalchemy import select
from app.models.d1_users import User
# 复用 conftest 的 client / _async_session_factory / 登录 helper（按现有 test_teacher_p0 同款）

@pytest.mark.asyncio
async def test_admin_lists_draft_and_publishes(client):
    # 1) 造一个 platform_admin（登录 + 改 role），造 1 个 KP + 1 道 draft 题
    # 2) GET /api/v1/admin/questions?status=draft&kp_id=... → total>=1，含 answer
    # 3) POST /api/v1/admin/questions/{id}/review {"approve": true} → status=published
    # 4) 学生端 GET /api/v1/kp/{kp_id}/practice-questions 现在能看到这道题
    ...

@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    # 普通用户 token 调 GET /api/v1/admin/questions → 403
    ...
```

> 实现者：照搬 `test_teacher_p0.py` 顶部的 fixture/helper import 与 admin 提权写法，保持与现有测试一致；KP 与 draft 题可直接用 `_async_session_factory()` + `question_service.persist_questions(...)`（默认 draft）落库。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/api/test_admin_questions.py -v`
Expected: FAIL（端点未注册 / 404）。

- [ ] **Step 3: 实现 schema + 端点**

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/api/test_admin_questions.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/questions.py backend/app/api/v1/admin.py tests/api/test_admin_questions.py
git commit -m "feat(backend): 运营 admin 仿真题审核 API（待审列表 + 通过/驳回）"
```

### Task 4: 全量验证 + 归档 D-095

- [ ] **Step 1: 后端全量测试绿**

Run: `python -m pytest -q`
Expected: 全 PASS（原 305 + 本次新增）。若有"persist 后默认 draft"引发的遗漏断言，回到 Task 1 Step 4 补显式 `status="published"`。

- [ ] **Step 2: docs/决策归档.md 顶部加 D-095**

格式同既往（日期/背景/结论/测试/影响范围/相关），编号递增；要点：persist 默认 draft + 审核 service + admin API 两端点 + 学生端只见 published 闸门闭环；明确"M5 仅做后端 admin API，Web 后台 UI 留后续"。

- [ ] **Step 3: Commit +（征得同意后）push**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-095 M5 仿真题审核发布流 admin API"
# push 需用户明确同意后再执行
```
