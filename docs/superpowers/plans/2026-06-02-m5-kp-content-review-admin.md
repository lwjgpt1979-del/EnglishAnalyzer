# M5 知识点内容审核/编辑（运营 admin API）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 把知识点 4 维度内容（`knowledge_point_contents`）纳入"AI 草稿 → 运营审核/编辑 → published"半自动质检流，并补齐运营 admin API（待审列表 + 审核通过/驳回 + 编辑正文），让运营在内容对学生可见前把关。镜像 D-095 仿真题审核流。

**Architecture:** 纯后端，零 DB 迁移（`content_status` enum `draft/reviewing/published/retired` 已存在）。当前学生端 `get_kp_contents` **未按 status 过滤**——本计划补上 `published` 出口闸门；`persist_unit` 内容默认改 `draft`（seed/测试显式传 `published`）；新增 service 审核/编辑读写函数；在既有 `api/v1/admin.py` 加 3 个端点。

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic v2；pytest（httpx AsyncClient）。

---

### Task 1: 出口闸门 + 内容 persist 默认草稿

**Files:**
- Modify: `backend/app/services/curriculum_service.py`（`get_kp_contents` 加 published 过滤；`persist_unit` 加 `content_status` 参数默认 `"draft"`）
- Modify: `backend/scripts/seed_curriculum.py:60`（persist_unit 传 `content_status="published"`）
- Modify: `tests/api/test_curriculum.py:43-57`（`_seed_unit` persist 传 `content_status="published"`）
- Test: `tests/api/test_curriculum.py`（新增 service 级过滤/默认草稿测试）

- [ ] **Step 1: 写失败测试**（放在 test_curriculum.py 末尾；`_seed_unit` 用 unit_no=1 免费单元绕过购买）

```python
@pytest.mark.asyncio
async def test_get_kp_contents_filters_published(client):
    """get_kp_contents 只返回 published 内容；draft 不对学生可见。"""
    import uuid as _uuid
    from app.models.d4_knowledge import KnowledgePoint, UnitKnowledgePoint
    from app.models.d11_v2_curriculum import CurriculumUnit, KnowledgePointContent
    from app.services import curriculum_service
    async with _async_session_factory() as s:
        cu = CurriculumUnit(
            id=_uuid.uuid4(), textbook_version="译林版", grade="小学5年级",
            semester="上", unit_no=1, title="免费单元",
        )
        s.add(cu); await s.flush()
        kp = KnowledgePoint(
            id=_uuid.uuid4(), code=f"flt-{_uuid.uuid4().hex[:6]}", name="过滤测试KP",
            category="grammar", description="d",
            applicable_grades=["小学5年级"], applicable_textbooks=["译林版"],
        )
        s.add(kp); await s.flush()
        s.add(UnitKnowledgePoint(unit_id=cu.id, knowledge_point_id=kp.id))
        s.add(KnowledgePointContent(
            id=_uuid.uuid4(), knowledge_point_id=kp.id, dimension="grammar",
            content_md="published grammar", status="published", generated_by="ai_full",
        ))
        s.add(KnowledgePointContent(
            id=_uuid.uuid4(), knowledge_point_id=kp.id, dimension="listening",
            content_md="draft listening", status="draft", generated_by="ai_full",
        ))
        await s.commit()
        kp_id = kp.id

    async with _async_session_factory() as s:
        contents = await curriculum_service.get_kp_contents(
            s, user_id=_uuid.uuid4(), kp_id=kp_id,
        )
    dims = {c.dimension for c in contents}
    assert dims == {"grammar"}        # 只剩 published 的 grammar，draft listening 被过滤


@pytest.mark.asyncio
async def test_persist_unit_content_defaults_draft(client):
    """persist_unit 不传 content_status 时，内容默认进 draft。"""
    import uuid as _uuid
    from sqlalchemy import select
    from app.models.d4_knowledge import KnowledgePoint, UnitKnowledgePoint
    from app.models.d11_v2_curriculum import CurriculumUnit, KnowledgePointContent
    from app.services import curriculum_ai_service, curriculum_service
    async with _async_session_factory() as s:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="小学5年级", semester="上", unit_no=18,
        )
        cu = await curriculum_service.persist_unit(s, ai_unit=ai)  # 默认 draft
        await s.commit()
        rows = (await s.execute(
            select(KnowledgePointContent)
            .join(UnitKnowledgePoint,
                  UnitKnowledgePoint.knowledge_point_id == KnowledgePointContent.knowledge_point_id)
            .where(UnitKnowledgePoint.unit_id == cu.id)
        )).scalars().all()
    assert rows and all(str(r.status) == "draft" for r in rows)
```

- [ ] **Step 2: 跑测试确认失败**

Run（cwd=backend）：`/opt/anaconda3/bin/python -m pytest ../tests/api/test_curriculum.py -k "filters_published or defaults_draft" -q`
Expected: FAIL（当前无 status 过滤、persist_unit 写 published）。

- [ ] **Step 3: 实现**
  - `get_kp_contents` 的 contents 查询加 `.where(KnowledgePointContent.status == "published")`。
  - `persist_unit(db, *, ai_unit, content_status: str = "draft")`，新建 `KnowledgePointContent(...)` 的 `status=content_status`（更新分支 `kpc.content_md = md` 不改 status）。

- [ ] **Step 4: 修复受影响调用方**
  - `seed_curriculum.py:60`：`await curriculum_service.persist_unit(db, ai_unit=ai, content_status="published")`。
  - `tests/api/test_curriculum.py` 的 `_seed_unit`：`await curriculum_service.persist_unit(s, ai_unit=ai, content_status="published")`（保证既有 `test_get_kp_contents_returns_4_dimensions` 仍见 4 维度）。

- [ ] **Step 5: 跑相关测试确认通过**

Run: `/opt/anaconda3/bin/python -m pytest ../tests/api/test_curriculum.py -q`
Expected: 全 PASS（含新增 2 例）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/curriculum_service.py backend/scripts/seed_curriculum.py tests/api/test_curriculum.py
git commit -m "feat(backend): 知识点内容 persist 默认草稿 + 学生端只见 published（M5 内容闸门）"
```

### Task 2: Service —— 内容待审列表 + 审核 + 编辑

**Files:**
- Modify: `backend/app/services/curriculum_service.py`
- Test: `tests/api/test_curriculum.py`

新增 3 个 service 函数：

```python
async def list_contents_for_review(
    db: AsyncSession, *, status: str = "draft",
    kp_id: uuid.UUID | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[KnowledgePointContent], int]:
    """运营按状态分页查知识点内容（返回完整 ORM 行）。"""
    base = select(KnowledgePointContent).where(KnowledgePointContent.status == status)
    if kp_id is not None:
        base = base.where(KnowledgePointContent.knowledge_point_id == kp_id)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(KnowledgePointContent.created_at).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def review_content(
    db: AsyncSession, *, content_id: uuid.UUID, approve: bool,
    reviewer_id: uuid.UUID,
) -> KnowledgePointContent:
    """审核一条内容：approve→published，reject→retired。记录 reviewed_by/at。"""
    c = (await db.execute(
        select(KnowledgePointContent).where(KnowledgePointContent.id == content_id)
    )).scalar_one_or_none()
    if c is None:
        raise AppError(code=404, message="内容不存在")
    c.status = "published" if approve else "retired"
    c.reviewed_by = reviewer_id
    c.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return c


async def update_content(
    db: AsyncSession, *, content_id: uuid.UUID,
    content_md: str | None = None, audio_url: str | None = None,
) -> KnowledgePointContent:
    """编辑内容正文 / 音频 URL（运营人工修订）。仅更新传入字段。"""
    c = (await db.execute(
        select(KnowledgePointContent).where(KnowledgePointContent.id == content_id)
    )).scalar_one_or_none()
    if c is None:
        raise AppError(code=404, message="内容不存在")
    if content_md is not None:
        c.content_md = content_md
        c.generated_by = "ai_with_human_review"
    if audio_url is not None:
        c.audio_url = audio_url
    await db.flush()
    return c
```

> 确认文件顶部已 `from datetime import datetime, timezone`、`from sqlalchemy import func, select`、`from app.core.exceptions import AppError`（缺哪个补哪个）。

- [ ] **Step 1: 写失败测试**（待审列表按状态过滤、审核通过→published 且写 reviewed_by、驳回→retired、编辑正文改 content_md 且 generated_by 变 ai_with_human_review、不存在抛 AppError）。helper：直接建 KP + KnowledgePointContent(draft) 行。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 3 函数**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit** `feat(backend): 知识点内容审核/编辑 service（待审列表+通过/驳回+编辑正文）`

### Task 3: Schemas + Admin API 端点

**Files:**
- Modify: `backend/app/schemas/curriculum.py`（加运营 DTO）
- Modify: `backend/app/api/v1/admin.py`（加 3 端点）
- Test: `tests/api/test_admin_contents.py`（新建）

新增 schema（`schemas/curriculum.py`）：

```python
class AdminContentItem(BaseModel):
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    dimension: str
    content_md: str
    audio_url: str | None = None
    status: str
    generated_by: str

class AdminContentListOut(BaseModel):
    total: int
    items: list[AdminContentItem]

class ContentReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")

class ContentUpdateRequest(BaseModel):
    content_md: str | None = Field(None, min_length=1)
    audio_url: str | None = None
```
（确认 `schemas/curriculum.py` 顶部有 `import uuid` 与 `from pydantic import BaseModel, Field`。）

新增端点（`api/v1/admin.py`，复用 `AdminDep`/`DbDep`；加 `_to_content_item` helper）：

```python
@router.get("/contents", response_model=BaseResponse[AdminContentListOut])
async def list_contents_for_review(db: DbDep, admin: AdminDep,
    status: str = "draft", kp_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20):
    rows, total = await curriculum_service.list_contents_for_review(
        db, status=status, kp_id=kp_id, skip=skip, limit=limit)
    return make_ok(AdminContentListOut(total=total, items=[_to_content_item(r) for r in rows]))

@router.post("/contents/{content_id}/review", response_model=BaseResponse[AdminContentItem])
async def review_content(content_id: uuid.UUID, body: ContentReviewRequest,
    db: DbDep, admin: AdminDep):
    r = await curriculum_service.review_content(
        db, content_id=content_id, approve=body.approve, reviewer_id=admin.id)
    await db.commit()
    return make_ok(_to_content_item(r))

@router.put("/contents/{content_id}", response_model=BaseResponse[AdminContentItem])
async def update_content(content_id: uuid.UUID, body: ContentUpdateRequest,
    db: DbDep, admin: AdminDep):
    r = await curriculum_service.update_content(
        db, content_id=content_id, content_md=body.content_md, audio_url=body.audio_url)
    await db.commit()
    return make_ok(_to_content_item(r))
```

- [ ] **Step 1: 写失败测试** `tests/api/test_admin_contents.py`（镜像 `test_admin_questions.py`：建 admin + 1 条 draft 内容 → GET /admin/contents 看到含正文 → PUT 改正文 → POST review approve → published；非管理员 403）。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 schema + 端点 + helper**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit** `feat(backend): 运营 admin 知识点内容审核/编辑 API`

### Task 4: 全量验证 + 归档 D-096

- [ ] **Step 1: 后端全量测试绿** `/opt/anaconda3/bin/python -m pytest ../tests -q`（期望 314 + 本次新增 全 PASS）
- [ ] **Step 2: docs/决策归档.md 顶部加 D-096**（格式同 D-095；要点：内容闸门 + persist 默认 draft + 审核/编辑 service + 3 个 admin 端点 + 学生端只见 published；编辑正文将 generated_by 标 ai_with_human_review；明确 M5 仍剩定价配置 admin API + Web 后台 UI）
- [ ] **Step 3: Commit +（征得同意后）push**
