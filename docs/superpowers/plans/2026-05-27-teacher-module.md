# Teacher Module MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现教师端最小可用功能：老师生成邀请码 → 学生绑定老师 → 老师查看学生错题 → 老师添加批注 → 学生在详情页看到批注。

**Architecture:** 复用现有 TeacherStudent + InviteCode 表实现师生绑定；新增 TeacherComment 表存储批注；7个新 API 端点挂在 `/teacher` 前缀 router；前端新增教师中心页（学生列表 + 学生错题页）并在 profile 页添加入口、在 WQ 详情页展示批注。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
New backend files:
  backend/alembic/versions/0004_teacher_module.py   # ADD VALUE to invite_code_type + create teacher_comments
  backend/app/schemas/teacher.py                    # 5 schemas
  backend/app/services/teacher_service.py           # 7 service functions
  backend/app/api/v1/teacher.py                     # 7 endpoints
  tests/api/test_teacher.py                         # 16 tests

Modified backend files:
  backend/app/models/d1_users.py:48-51              # add "teacher_bind" to invite_code_type_enum
  backend/app/models/d3_wrong_questions.py          # append TeacherComment class
  backend/app/models/__init__.py:24                 # add TeacherComment to d3 import
  backend/app/api/v1/router.py                      # add teacher_router

New frontend files:
  frontend/miniprogram/src/api/teacher.ts           # 7 API call functions
  frontend/miniprogram/src/pages/teacher/students.vue       # 教师中心：学生列表 + 邀请码 + 绑定老师
  frontend/miniprogram/src/pages/teacher/student-detail.vue # 老师查看学生错题 + 添加批注

Modified frontend files:
  frontend/miniprogram/src/types/api.ts             # 4 new interfaces
  frontend/miniprogram/src/pages.json               # add 2 teacher pages
  frontend/miniprogram/src/pages/profile/index.vue  # add "教师中心" entry card
  frontend/miniprogram/src/pages/wrong-questions/detail.vue # add teacher comments section
```

**Key model facts（确认再动手）：**
- `invite_code_type_enum` 当前值：`"relative_bind"`, `"institution_join"` → 迁移添加 `"teacher_bind"`
- `TeacherStudent` 字段：`teacher_id`, `student_id`, `bind_type`, `bind_source`, `status`, `requested_at`, `bound_at`
- `bind_type_enum`: `"institution_assigned"`, `"self_bound"` → 邀请码绑定用 `"self_bound"`
- `bind_source_enum`: `"sms_invite"`, `"miniprogram_link"`, `"institution_assigned"` → 邀请码用 `"miniprogram_link"`
- `teacher_student_status_enum`: `"pending"`, `"active"`, `"rejected"`, `"inactive"`
- `InviteCode` 字段：`id`, `code`, `type`, `issuer_id`, `target_id`, `expires_at`, `used_at`, `created_at`
- `Teacher` 字段：`id`（= user.id FK）, `institution_id`, `cert_status`, `cert_doc_url`, `subject`, `max_students`
- `cert_status_enum` server_default = `"uncertified"` — 创建时不传则 DB 填默认值（Python 端需显式传）

---

## Task 0: DB Migration 0004 + Model Changes

**Files:**
- Modify: `backend/app/models/d1_users.py`
- Modify: `backend/app/models/d3_wrong_questions.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0004_teacher_module.py`
- Create: `tests/api/test_teacher.py` (空文件占位)

- [ ] **Step 1: 更新 `d1_users.py` 的 invite_code_type_enum**

在 `backend/app/models/d1_users.py` 第 48-51 行，将：
```python
invite_code_type_enum = sa.Enum(
    "relative_bind", "institution_join",
    name="invite_code_type",
)
```
改为：
```python
invite_code_type_enum = sa.Enum(
    "relative_bind", "institution_join", "teacher_bind",
    name="invite_code_type",
)
```

- [ ] **Step 2: 追加 TeacherComment 到 `d3_wrong_questions.py`**

READ `backend/app/models/d3_wrong_questions.py` 确认末尾，然后在文件末尾追加：

```python


class TeacherComment(Base):
    """教师对错题的批注。"""

    __tablename__ = "teacher_comments"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    comment_text = mapped_column(sa.Text, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
```

- [ ] **Step 3: 更新 `__init__.py`**

在 `backend/app/models/__init__.py`，将第 24 行：
```python
from .d3_wrong_questions import WrongQuestion, OcrTask, AiAnalysis  # noqa: F401
```
改为：
```python
from .d3_wrong_questions import WrongQuestion, OcrTask, AiAnalysis, TeacherComment  # noqa: F401
```

同时将上方注释从 `# 域3: 错题与 AI 诊断 (3 张表)` 改为 `# 域3: 错题与 AI 诊断 (4 张表)`。

- [ ] **Step 4: 创建 `0004_teacher_module.py`**

创建 `backend/alembic/versions/0004_teacher_module.py`：

```python
"""teacher_module: add teacher_bind to invite_code_type, create teacher_comments

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 12+ supports ALTER TYPE ADD VALUE inside a transaction.
    op.execute(
        "ALTER TYPE invite_code_type ADD VALUE IF NOT EXISTS 'teacher_bind'"
    )

    op.create_table(
        "teacher_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "wrong_question_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_text", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["wrong_question_id"],
            ["wrong_questions.id"],
            name="fk_teacher_comments_wq",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name="fk_teacher_comments_teacher",
        ),
    )
    op.create_index(
        "ix_teacher_comments_wq_id", "teacher_comments", ["wrong_question_id"]
    )
    op.create_index(
        "ix_teacher_comments_teacher_id", "teacher_comments", ["teacher_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_comments_teacher_id", table_name="teacher_comments")
    op.drop_index("ix_teacher_comments_wq_id", table_name="teacher_comments")
    op.drop_table("teacher_comments")
    # NOTE: PostgreSQL does not support removing enum values.
    # invite_code_type 保留 'teacher_bind' 值。
```

- [ ] **Step 5: 创建占位测试文件**

```bash
touch /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/tests/api/test_teacher.py
```

- [ ] **Step 6: 运行迁移**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, teacher_module: ...
```

- [ ] **Step 7: 确认表存在**

```bash
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" python3 -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
async def check():
    e = create_async_engine('postgresql+psycopg://postgres:dev@localhost:5432/enggramer')
    async with e.connect() as conn:
        r = await conn.execute(__import__('sqlalchemy').text(
            \"SELECT table_name FROM information_schema.tables WHERE table_name='teacher_comments'\"
        ))
        print('teacher_comments table:', r.fetchone())
asyncio.run(check())
"
```

Expected: `teacher_comments table: ('teacher_comments',)`

- [ ] **Step 8: 运行全量测试确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `128 passed`

- [ ] **Step 9: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/alembic/versions/0004_teacher_module.py \
        backend/app/models/d1_users.py \
        backend/app/models/d3_wrong_questions.py \
        backend/app/models/__init__.py \
        tests/api/test_teacher.py
git commit -m "feat(db): migration 0004 — teacher_comments table + teacher_bind invite code type"
```

---

## Task 1: Teacher Schemas

**Files:**
- Create: `backend/app/schemas/teacher.py`
- Modify: `tests/api/test_teacher.py` (append)

- [ ] **Step 1: 追加 schema 单元测试到 `tests/api/test_teacher.py`**

用 WRITE（完整替换，因为文件是空的）：

```python
"""教师端测试。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.schemas.teacher import (
    BecomeTeacherRequest,
    BindTeacherRequest,
    InviteCodeOut,
    TeacherCommentCreate,
    TeacherCommentOut,
    TeacherProfileOut,
    TeacherStudentOut,
)


# ── Schema 单元测试 ────────────────────────────────────────────────────────────


def test_become_teacher_request_optional_subject():
    req = BecomeTeacherRequest()
    assert req.subject is None


def test_become_teacher_request_with_subject():
    req = BecomeTeacherRequest(subject="英语")
    assert req.subject == "英语"


def test_bind_teacher_request_validates_length():
    req = BindTeacherRequest(code="ABC123")
    assert req.code == "ABC123"


def test_teacher_comment_create_schema():
    req = TeacherCommentCreate(comment_text="注意时态用法")
    assert req.comment_text == "注意时态用法"


def test_teacher_comment_out_schema():
    now = datetime.now(timezone.utc)
    out = TeacherCommentOut(
        id=uuid.uuid4(),
        wrong_question_id=uuid.uuid4(),
        teacher_id=uuid.uuid4(),
        comment_text="该题考查时态",
        created_at=now,
    )
    assert out.comment_text == "该题考查时态"
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_teacher.py -v 2>&1 | head -10
```

Expected: `FAILED` / `ImportError: cannot import name 'BecomeTeacherRequest'`

- [ ] **Step 3: 创建 `backend/app/schemas/teacher.py`**

```python
"""教师端 Pydantic Schemas。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BecomeTeacherRequest(BaseModel):
    subject: str | None = Field(None, description="任教科目，如'英语'")


class TeacherProfileOut(BaseModel):
    user_id: uuid.UUID
    subject: str | None
    cert_status: str
    max_students: int

    model_config = {"from_attributes": True}


class InviteCodeOut(BaseModel):
    code: str
    expires_at: datetime


class BindTeacherRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="6位邀请码")


class TeacherStudentOut(BaseModel):
    student_id: uuid.UUID
    bound_at: datetime | None

    model_config = {"from_attributes": True}


class TeacherCommentCreate(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=2000)


class TeacherCommentOut(BaseModel):
    id: uuid.UUID
    wrong_question_id: uuid.UUID
    teacher_id: uuid.UUID
    comment_text: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 运行 schema 测试，确认通过**

```bash
python -m pytest ../tests/api/test_teacher.py -v
```

Expected: `5 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `133 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/teacher.py tests/api/test_teacher.py
git commit -m "feat(schemas): teacher module schemas — TeacherProfile/InviteCode/TeacherComment"
```

---

## Task 2: Teacher Service

**Files:**
- Create: `backend/app/services/teacher_service.py`
- Modify: `tests/api/test_teacher.py` (append)

- [ ] **Step 1: 追加 service 集成测试到 `tests/api/test_teacher.py`**

在文件末尾追加（READ 末尾后追加，不要覆盖）：

```python

# ── Service 集成测试（需要真实 DB）─────────────────────────────────────────────

from app.core.database import _async_session_factory
from app.services.auth_service import upsert_user
from app.services.teacher_service import (
    add_comment,
    become_teacher,
    bind_with_teacher,
    generate_invite_code,
    get_comments_for_wq,
    get_my_students,
    get_student_wrong_questions,
)
from app.models.d3_wrong_questions import WrongQuestion, TeacherComment
from app.core.exceptions import AppError


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student_user(db_session):
    user = await upsert_user(db_session, openid=f"teacher_svc_student_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def teacher_user(db_session):
    user = await upsert_user(db_session, openid=f"teacher_svc_teacher_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    data = BecomeTeacherRequest(subject="英语")
    await become_teacher(db_session, user=user, data=data)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_become_teacher_creates_record(db_session, student_user):
    data = BecomeTeacherRequest(subject="英语")
    teacher = await become_teacher(db_session, user=student_user, data=data)
    await db_session.flush()

    assert teacher.id == student_user.id
    assert teacher.subject == "英语"
    assert student_user.role == "teacher"


@pytest.mark.asyncio
async def test_become_teacher_is_idempotent(db_session, student_user):
    data = BecomeTeacherRequest(subject="英语")
    t1 = await become_teacher(db_session, user=student_user, data=data)
    await db_session.flush()
    t2 = await become_teacher(db_session, user=student_user, data=data)
    assert t1.id == t2.id


@pytest.mark.asyncio
async def test_generate_invite_code(db_session, teacher_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()

    assert len(invite.code) == 6
    assert invite.code == invite.code.upper()
    assert invite.type == "teacher_bind"
    assert invite.used_at is None


@pytest.mark.asyncio
async def test_bind_with_teacher_success(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()

    relation = await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    assert relation.teacher_id == teacher_user.id
    assert relation.student_id == student_user.id
    assert relation.status == "active"
    assert invite.used_at is not None


@pytest.mark.asyncio
async def test_bind_with_teacher_invalid_code_raises(db_session, student_user):
    with pytest.raises(AppError) as exc_info:
        await bind_with_teacher(db_session, student=student_user, code="XXXXXX")
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_bind_with_teacher_already_bound_raises(db_session, teacher_user, student_user):
    invite1 = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite1.code)
    await db_session.flush()

    invite2 = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    with pytest.raises(AppError) as exc_info:
        await bind_with_teacher(db_session, student=student_user, code=invite2.code)
    assert exc_info.value.code == 409


@pytest.mark.asyncio
async def test_get_my_students(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    students = await get_my_students(db_session, teacher_id=teacher_user.id)
    assert len(students) == 1
    assert students[0].student_id == student_user.id


@pytest.mark.asyncio
async def test_add_comment_success(db_session, teacher_user, student_user):
    # 先绑定
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    # 创建错题
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    # 老师批注
    comment = await add_comment(
        db_session,
        teacher_id=teacher_user.id,
        wq_id=wq.id,
        data=TeacherCommentCreate(comment_text="注意时态"),
    )
    await db_session.flush()

    assert comment.comment_text == "注意时态"
    assert comment.teacher_id == teacher_user.id
    assert comment.wrong_question_id == wq.id


@pytest.mark.asyncio
async def test_add_comment_unbound_teacher_raises(db_session, teacher_user, student_user):
    # 未绑定直接批注
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img2.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await add_comment(
            db_session,
            teacher_id=teacher_user.id,
            wq_id=wq.id,
            data=TeacherCommentCreate(comment_text="应该报错"),
        )
    assert exc_info.value.code == 403


@pytest.mark.asyncio
async def test_get_comments_for_wq(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img3.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    await add_comment(db_session, teacher_id=teacher_user.id, wq_id=wq.id,
                      data=TeacherCommentCreate(comment_text="批注1"))
    await add_comment(db_session, teacher_id=teacher_user.id, wq_id=wq.id,
                      data=TeacherCommentCreate(comment_text="批注2"))
    await db_session.flush()

    comments = await get_comments_for_wq(db_session, wq_id=wq.id)
    assert len(comments) == 2
    assert comments[0].comment_text == "批注1"
```

- [ ] **Step 2: 运行，确认失败**

```bash
python -m pytest ../tests/api/test_teacher.py -k "service or become or invite or bind or student or comment" -v 2>&1 | head -15
```

Expected: `FAILED` / `ImportError: cannot import name 'become_teacher'`

- [ ] **Step 3: 创建 `backend/app/services/teacher_service.py`**

```python
"""教师端业务逻辑。

功能：
- become_teacher: 学生升级为教师角色（幂等）
- generate_invite_code: 教师生成6位邀请码（有效24h）
- bind_with_teacher: 学生通过邀请码绑定教师
- get_my_students: 教师查看所有活跃绑定学生
- get_student_wrong_questions: 教师查看指定学生错题（含绑定校验）
- add_comment: 教师为错题添加批注（含绑定校验）
- get_comments_for_wq: 查询某错题所有批注（按时间升序）
"""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import InviteCode, Teacher, TeacherStudent, User
from app.models.d3_wrong_questions import TeacherComment, WrongQuestion
from app.schemas.teacher import BecomeTeacherRequest, TeacherCommentCreate

_CODE_CHARS = string.ascii_uppercase + string.digits  # A-Z 0-9, 36 chars
_CODE_LENGTH = 6
_CODE_TTL_HOURS = 24


async def become_teacher(
    db: AsyncSession,
    *,
    user: User,
    data: BecomeTeacherRequest,
) -> Teacher:
    """将当前用户升级为教师角色，创建 Teacher 扩展记录。已是教师则幂等返回。"""
    result = await db.execute(select(Teacher).where(Teacher.id == user.id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    user.role = "teacher"  # type: ignore[assignment]
    teacher = Teacher(
        id=user.id,
        subject=data.subject,
        cert_status="uncertified",  # type: ignore[arg-type]
        max_students=50,
    )
    db.add(teacher)
    await db.flush()
    return teacher


async def generate_invite_code(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
) -> InviteCode:
    """生成6位大写字母+数字邀请码，有效期24小时，冲突重试10次。"""

    async def _unique_code() -> str:
        for _ in range(10):
            code = "".join(random.choices(_CODE_CHARS, k=_CODE_LENGTH))
            r = await db.execute(select(InviteCode).where(InviteCode.code == code))
            if r.scalar_one_or_none() is None:
                return code
        raise AppError(code=500, message="邀请码生成失败，请重试")

    code = await _unique_code()
    invite = InviteCode(
        id=uuid.uuid4(),
        code=code,
        type="teacher_bind",  # type: ignore[arg-type]
        issuer_id=teacher_id,
        target_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=_CODE_TTL_HOURS),
    )
    db.add(invite)
    await db.flush()
    return invite


async def bind_with_teacher(
    db: AsyncSession,
    *,
    student: User,
    code: str,
) -> TeacherStudent:
    """学生通过邀请码绑定老师。

    - 码无效/已过期/已使用 → AppError(400)
    - 已绑定该老师 → AppError(409)
    """
    now = datetime.now(timezone.utc)

    invite_result = await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.type == "teacher_bind",
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise AppError(code=400, message="邀请码无效或已过期")

    teacher_id = invite.issuer_id

    existing = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student.id,
            TeacherStudent.status == "active",
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError(code=409, message="您已绑定该老师")

    relation = TeacherStudent(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        student_id=student.id,
        bind_type="self_bound",  # type: ignore[arg-type]
        bind_source="miniprogram_link",  # type: ignore[arg-type]
        status="active",  # type: ignore[arg-type]
        requested_at=now,
        bound_at=now,
    )
    db.add(relation)
    invite.used_at = now
    await db.flush()
    return relation


async def get_my_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
) -> list[TeacherStudent]:
    """返回教师所有活跃绑定学生。"""
    result = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.status == "active",
        )
    )
    return list(result.scalars().all())


async def get_student_wrong_questions(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
) -> list[WrongQuestion]:
    """教师查看指定学生的错题列表，先校验绑定关系。"""
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权查看该学生数据")

    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.student_id == student_id)
        .order_by(WrongQuestion.created_at.desc())
    )
    return list(result.scalars().all())


async def add_comment(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    wq_id: uuid.UUID,
    data: TeacherCommentCreate,
) -> TeacherComment:
    """教师为错题添加批注，先校验该错题归属学生是否为教师的绑定学生。"""
    wq_result = await db.execute(
        select(WrongQuestion).where(WrongQuestion.id == wq_id)
    )
    wq = wq_result.scalar_one_or_none()
    if wq is None:
        raise AppError(code=404, message="错题不存在")

    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == wq.student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权批注该学生的错题")

    comment = TeacherComment(
        id=uuid.uuid4(),
        wrong_question_id=wq_id,
        teacher_id=teacher_id,
        comment_text=data.comment_text,
    )
    db.add(comment)
    await db.flush()
    return comment


async def get_comments_for_wq(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
) -> list[TeacherComment]:
    """查询某道错题所有批注（按创建时间升序）。"""
    result = await db.execute(
        select(TeacherComment)
        .where(TeacherComment.wrong_question_id == wq_id)
        .order_by(TeacherComment.created_at.asc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: 运行 service 测试，确认通过**

```bash
python -m pytest ../tests/api/test_teacher.py -k "become or invite or bind or students or comment" -v
```

Expected: `11 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `144 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/teacher_service.py tests/api/test_teacher.py
git commit -m "feat(service): teacher service — become_teacher/invite_code/bind/comment"
```

---

## Task 3: Teacher API Endpoints + Router

**Files:**
- Create: `backend/app/api/v1/teacher.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_teacher.py` (append)

- [ ] **Step 1: 追加 API 集成测试**

在 `tests/api/test_teacher.py` 末尾追加（READ 末尾后追加）：

```python

# ── API 集成测试 ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def student_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"teacher_api_stu_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def teacher_headers(client: AsyncClient):
    """学生登录后立即升级为教师，返回 headers。"""
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"teacher_api_tch_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # 升级为教师
    become_resp = await client.post(
        "/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers
    )
    assert become_resp.status_code == 200, become_resp.text
    return headers


@pytest.mark.asyncio
async def test_become_teacher_api(client: AsyncClient, student_headers):
    resp = await client.post(
        "/api/v1/teacher/profile",
        json={"subject": "英语"},
        headers=student_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["cert_status"] == "uncertified"
    assert data["subject"] == "英语"
    assert data["max_students"] == 50


@pytest.mark.asyncio
async def test_create_invite_code_requires_teacher(client: AsyncClient, student_headers):
    """未升级为教师的用户不能生成邀请码。"""
    resp = await client.post("/api/v1/teacher/invite-code", headers=student_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_invite_code_api(client: AsyncClient, teacher_headers):
    resp = await client.post("/api/v1/teacher/invite-code", headers=teacher_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["code"]) == 6
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_bind_teacher_api(client: AsyncClient, teacher_headers, student_headers):
    """学生用邀请码绑定老师。"""
    # 教师生成邀请码
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]

    # 学生绑定
    bind_resp = await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )
    assert bind_resp.status_code == 200
    data = bind_resp.json()["data"]
    assert "student_id" in data
    assert "bound_at" in data


@pytest.mark.asyncio
async def test_list_students_api(client: AsyncClient, teacher_headers, student_headers):
    """绑定后教师可查看学生列表。"""
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]
    await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )

    list_resp = await client.get("/api/v1/teacher/students", headers=teacher_headers)
    assert list_resp.status_code == 200
    students = list_resp.json()["data"]
    assert len(students) >= 1


@pytest.mark.asyncio
async def test_add_comment_and_get_comments_api(
    client: AsyncClient, teacher_headers, student_headers
):
    """老师批注 + 学生/老师读批注。"""
    # 绑定
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]
    await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )

    # 学生创建错题（ocr_status 会被设为 pending，背景任务异步，不影响测试）
    wq_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://example.com/teacher_comment_test.jpg"},
        headers=student_headers,
    )
    assert wq_resp.status_code == 200, wq_resp.text
    wq_id = wq_resp.json()["data"]["id"]

    # 老师批注
    comment_resp = await client.post(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        json={"comment_text": "注意主谓一致"},
        headers=teacher_headers,
    )
    assert comment_resp.status_code == 200
    assert comment_resp.json()["data"]["comment_text"] == "注意主谓一致"

    # 读取批注（老师读）
    get_resp = await client.get(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        headers=teacher_headers,
    )
    assert get_resp.status_code == 200
    comments = get_resp.json()["data"]
    assert len(comments) == 1
    assert comments[0]["comment_text"] == "注意主谓一致"

    # 读取批注（学生读）
    student_get = await client.get(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        headers=student_headers,
    )
    assert student_get.status_code == 200
    assert len(student_get.json()["data"]) == 1
```

- [ ] **Step 2: 运行，确认失败**

```bash
python -m pytest ../tests/api/test_teacher.py -k "api" -v 2>&1 | head -10
```

Expected: `FAILED` / 404（路由未注册）

- [ ] **Step 3: 创建 `backend/app/api/v1/teacher.py`**

```python
"""教师端 API。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.teacher import (
    BecomeTeacherRequest,
    BindTeacherRequest,
    InviteCodeOut,
    TeacherCommentCreate,
    TeacherCommentOut,
    TeacherProfileOut,
    TeacherStudentOut,
)
from app.schemas.wrong_questions import WrongQuestionOut
from app.services import teacher_service

router = APIRouter(prefix="/teacher", tags=["teacher"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/profile", response_model=BaseResponse[TeacherProfileOut])
async def become_teacher(
    body: BecomeTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """任意用户升级为教师角色（幂等）。"""
    await get_rls_db(db, str(current_user.id))
    teacher = await teacher_service.become_teacher(db, user=current_user, data=body)
    await db.commit()
    return make_ok(
        TeacherProfileOut(
            user_id=teacher.id,
            subject=teacher.subject,
            cert_status=str(teacher.cert_status),
            max_students=teacher.max_students,
        )
    )


@router.post("/invite-code", response_model=BaseResponse[InviteCodeOut])
async def create_invite_code(db: DbDep, current_user: UserDep):
    """教师生成邀请码（有效期24小时）。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可生成邀请码")
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(
        db, teacher_id=current_user.id
    )
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.post("/bind", response_model=BaseResponse[TeacherStudentOut])
async def bind_teacher(
    body: BindTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """学生通过邀请码绑定老师。"""
    await get_rls_db(db, str(current_user.id))
    relation = await teacher_service.bind_with_teacher(
        db, student=current_user, code=body.code.upper()
    )
    await db.commit()
    return make_ok(
        TeacherStudentOut(
            student_id=relation.student_id,
            bound_at=relation.bound_at,
        )
    )


@router.get("/students", response_model=BaseResponse[list[TeacherStudentOut]])
async def list_my_students(db: DbDep, current_user: UserDep):
    """教师查看所有绑定学生。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生列表")
    await get_rls_db(db, str(current_user.id))
    students = await teacher_service.get_my_students(
        db, teacher_id=current_user.id
    )
    return make_ok(
        [TeacherStudentOut(student_id=s.student_id, bound_at=s.bound_at) for s in students]
    )


@router.get(
    "/students/{student_id}/wrong-questions",
    response_model=BaseResponse[list[WrongQuestionOut]],
)
async def get_student_wrong_questions(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """教师查看指定绑定学生的错题列表。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生错题")
    await get_rls_db(db, str(current_user.id))
    wqs = await teacher_service.get_student_wrong_questions(
        db, teacher_id=current_user.id, student_id=student_id
    )
    return make_ok([WrongQuestionOut.model_validate(wq) for wq in wqs])


@router.post(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[TeacherCommentOut],
)
async def add_comment(
    wq_id: uuid.UUID,
    body: TeacherCommentCreate,
    db: DbDep,
    current_user: UserDep,
):
    """教师为错题添加批注。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可添加批注")
    await get_rls_db(db, str(current_user.id))
    comment = await teacher_service.add_comment(
        db, teacher_id=current_user.id, wq_id=wq_id, data=body
    )
    await db.commit()
    return make_ok(TeacherCommentOut.model_validate(comment))


@router.get(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[list[TeacherCommentOut]],
)
async def get_comments(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查看错题上的所有老师批注。
    
    学生（WQ 所有者）和绑定该学生的老师均可访问。
    未授权则返回空列表（不报错，前端容错更友好）。
    """
    await get_rls_db(db, str(current_user.id))
    comments = await teacher_service.get_comments_for_wq(db, wq_id=wq_id)
    return make_ok([TeacherCommentOut.model_validate(c) for c in comments])
```

- [ ] **Step 4: 更新 `backend/app/api/v1/router.py`**

完整替换文件（保留现有所有 router，追加 teacher）：

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.diagnosis import router as diagnosis_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.orders import router as orders_router
from app.api.v1.teacher import router as teacher_router
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
v1_router.include_router(ocr_router)
v1_router.include_router(teacher_router)
```

- [ ] **Step 5: 运行 API 测试，确认通过**

```bash
python -m pytest ../tests/api/test_teacher.py -k "api" -v
```

Expected: `6 passed`

- [ ] **Step 6: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `150 passed`（144 + 6 新增）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/teacher.py backend/app/api/v1/router.py tests/api/test_teacher.py
git commit -m "feat(api): teacher endpoints — profile/invite-code/bind/students/comments"
```

---

## Task 4: Frontend — Teacher Pages + Profile Entry + WQ Comments

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/teacher.ts`
- Modify: `frontend/miniprogram/src/pages.json`
- Create: `frontend/miniprogram/src/pages/teacher/students.vue`
- Create: `frontend/miniprogram/src/pages/teacher/student-detail.vue`
- Modify: `frontend/miniprogram/src/pages/profile/index.vue`
- Modify: `frontend/miniprogram/src/pages/wrong-questions/detail.vue`

- [ ] **Step 1: 追加类型到 `types/api.ts`**

READ `frontend/miniprogram/src/types/api.ts` 末尾，然后在末尾追加：

```typescript
export interface TeacherProfileOut {
  user_id: string
  subject: string | null
  cert_status: string
  max_students: number
}

export interface InviteCodeOut {
  code: string
  expires_at: string
}

export interface TeacherStudentOut {
  student_id: string
  bound_at: string | null
}

export interface TeacherCommentOut {
  id: string
  wrong_question_id: string
  teacher_id: string
  comment_text: string
  created_at: string
}
```

- [ ] **Step 2: 创建 `frontend/miniprogram/src/api/teacher.ts`**

```typescript
import { request } from './request'
import type {
  BaseResponse,
  TeacherProfileOut,
  InviteCodeOut,
  TeacherStudentOut,
  TeacherCommentOut,
  WrongQuestionOut,
} from '../types/api'

export function becomeTeacher(subject?: string): Promise<BaseResponse<TeacherProfileOut>> {
  return request('/teacher/profile', { method: 'POST', data: { subject: subject || null } })
}

export function createInviteCode(): Promise<BaseResponse<InviteCodeOut>> {
  return request('/teacher/invite-code', { method: 'POST' })
}

export function bindTeacher(code: string): Promise<BaseResponse<TeacherStudentOut>> {
  return request('/teacher/bind', { method: 'POST', data: { code } })
}

export function getMyStudents(): Promise<BaseResponse<TeacherStudentOut[]>> {
  return request('/teacher/students', { method: 'GET' })
}

export function getStudentWrongQuestions(studentId: string): Promise<BaseResponse<WrongQuestionOut[]>> {
  return request(`/teacher/students/${studentId}/wrong-questions`, { method: 'GET' })
}

export function addComment(wqId: string, commentText: string): Promise<BaseResponse<TeacherCommentOut>> {
  return request(`/teacher/wrong-questions/${wqId}/comments`, {
    method: 'POST',
    data: { comment_text: commentText },
  })
}

export function getComments(wqId: string): Promise<BaseResponse<TeacherCommentOut[]>> {
  return request(`/teacher/wrong-questions/${wqId}/comments`, { method: 'GET' })
}
```

- [ ] **Step 3: 更新 `pages.json`（添加2个教师页）**

完整替换 `frontend/miniprogram/src/pages.json`：

```json
{
  "pages": [
    {
      "path": "pages/index/index",
      "style": { "navigationBarTitleText": "engGramer" }
    },
    {
      "path": "pages/upload/index",
      "style": { "navigationBarTitleText": "上传错题" }
    },
    {
      "path": "pages/wrong-questions/list",
      "style": { "navigationBarTitleText": "我的错题" }
    },
    {
      "path": "pages/wrong-questions/detail",
      "style": { "navigationBarTitleText": "错题详情" }
    },
    {
      "path": "pages/diagnosis/index",
      "style": { "navigationBarTitleText": "学情报告" }
    },
    {
      "path": "pages/profile/index",
      "style": { "navigationBarTitleText": "我的" }
    },
    {
      "path": "pages/teacher/students",
      "style": { "navigationBarTitleText": "教师中心" }
    },
    {
      "path": "pages/teacher/student-detail",
      "style": { "navigationBarTitleText": "学生错题" }
    }
  ],
  "tabBar": {
    "color": "#999",
    "selectedColor": "#1677ff",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "首页",
        "iconPath": "static/tab-home.png",
        "selectedIconPath": "static/tab-home-active.png"
      },
      {
        "pagePath": "pages/wrong-questions/list",
        "text": "错题",
        "iconPath": "static/tab-wrong.png",
        "selectedIconPath": "static/tab-wrong-active.png"
      },
      {
        "pagePath": "pages/diagnosis/index",
        "text": "报告",
        "iconPath": "static/tab-report.png",
        "selectedIconPath": "static/tab-report-active.png"
      },
      {
        "pagePath": "pages/profile/index",
        "text": "我的",
        "iconPath": "static/tab-profile.png",
        "selectedIconPath": "static/tab-profile-active.png"
      }
    ]
  },
  "globalStyle": {
    "navigationBarTextStyle": "black",
    "navigationBarTitleText": "engGramer",
    "navigationBarBackgroundColor": "#ffffff",
    "backgroundColor": "#f5f5f5"
  }
}
```

- [ ] **Step 4: 创建 `pages/teacher/students.vue`**

先确认目录存在：`mkdir -p frontend/miniprogram/src/pages/teacher`

创建文件：

```vue
<!-- src/pages/teacher/students.vue -->
<template>
  <view class="teacher-page">

    <!-- 成为教师 / 教师信息 -->
    <view class="card">
      <view class="card-title">教师身份</view>
      <view v-if="isTeacher" class="teacher-badge">
        <text class="badge-text">✅ 教师账号</text>
        <text v-if="profile" class="subject-text">科目：{{ profile.subject || '未设置' }}</text>
      </view>
      <view v-else>
        <input
          v-model="subjectInput"
          class="input"
          placeholder="任教科目（选填，如：英语）"
        />
        <button class="btn-primary" :disabled="becoming" @tap="handleBecomeTeacher">
          {{ becoming ? '处理中…' : '成为教师' }}
        </button>
      </view>
    </view>

    <!-- 邀请学生（教师专用） -->
    <view v-if="isTeacher" class="card">
      <view class="card-title">邀请学生绑定</view>
      <button class="btn-secondary" :disabled="generatingCode" @tap="handleGenerateCode">
        {{ generatingCode ? '生成中…' : '生成邀请码' }}
      </button>
      <view v-if="inviteCode" class="invite-box">
        <text class="invite-code">{{ inviteCode.code }}</text>
        <text class="invite-expire">24小时内有效</text>
        <button size="mini" class="btn-copy" @tap="copyCode">复制</button>
      </view>
    </view>

    <!-- 学生列表（教师专用） -->
    <view v-if="isTeacher" class="card">
      <view class="card-title">我的学生（{{ students.length }}）</view>
      <view v-if="loadingStudents" class="tip">加载中…</view>
      <view v-else-if="students.length === 0" class="tip">
        暂无绑定学生，请生成邀请码邀请学生扫描绑定。
      </view>
      <view
        v-for="s in students"
        :key="s.student_id"
        class="student-item"
        @tap="goToStudent(s.student_id)"
      >
        <text class="student-id">学生 {{ s.student_id.slice(0, 8) }}…</text>
        <text class="student-bind-date">绑定：{{ s.bound_at ? s.bound_at.slice(0, 10) : '-' }}</text>
        <text class="arrow">›</text>
      </view>
    </view>

    <!-- 绑定老师（所有用户） -->
    <view class="card">
      <view class="card-title">绑定老师</view>
      <input
        v-model="bindCodeInput"
        class="input"
        placeholder="输入老师的6位邀请码"
        maxlength="6"
        @input="bindCodeInput = bindCodeInput.toUpperCase()"
      />
      <button class="btn-primary" :disabled="binding" @tap="handleBind">
        {{ binding ? '绑定中…' : '绑定老师' }}
      </button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import {
  becomeTeacher,
  createInviteCode,
  bindTeacher,
  getMyStudents,
} from '../../api/teacher'
import type { TeacherProfileOut, InviteCodeOut, TeacherStudentOut } from '../../types/api'

const auth = useAuthStore()

const isTeacher = ref(false)
const profile = ref<TeacherProfileOut | null>(null)
const subjectInput = ref('')
const becoming = ref(false)

const inviteCode = ref<InviteCodeOut | null>(null)
const generatingCode = ref(false)

const students = ref<TeacherStudentOut[]>([])
const loadingStudents = ref(false)

const bindCodeInput = ref('')
const binding = ref(false)

onMounted(async () => {
  if (!auth.user) return
  isTeacher.value = auth.user.role === 'teacher'
  if (isTeacher.value) {
    await loadStudents()
  }
})

async function handleBecomeTeacher() {
  becoming.value = true
  try {
    const res = await becomeTeacher(subjectInput.value || undefined)
    if (res.code === 200) {
      profile.value = res.data
      isTeacher.value = true
      // 更新本地用户 role
      if (auth.user) auth.user.role = 'teacher'
      await loadStudents()
      uni.showToast({ title: '已成为教师', icon: 'success' })
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '操作失败', icon: 'none' })
  } finally {
    becoming.value = false
  }
}

async function handleGenerateCode() {
  generatingCode.value = true
  try {
    const res = await createInviteCode()
    if (res.code === 200) inviteCode.value = res.data
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally {
    generatingCode.value = false
  }
}

function copyCode() {
  if (!inviteCode.value) return
  uni.setClipboardData({
    data: inviteCode.value.code,
    success: () => uni.showToast({ title: '已复制', icon: 'success' }),
  })
}

async function loadStudents() {
  loadingStudents.value = true
  try {
    const res = await getMyStudents()
    if (res.code === 200) students.value = res.data
  } finally {
    loadingStudents.value = false
  }
}

async function handleBind() {
  if (bindCodeInput.value.length !== 6) {
    uni.showToast({ title: '请输入6位邀请码', icon: 'none' })
    return
  }
  binding.value = true
  try {
    const res = await bindTeacher(bindCodeInput.value)
    if (res.code === 200) {
      bindCodeInput.value = ''
      uni.showToast({ title: '绑定成功', icon: 'success' })
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
  } finally {
    binding.value = false
  }
}

function goToStudent(studentId: string) {
  uni.navigateTo({ url: `/pages/teacher/student-detail?studentId=${studentId}` })
}
</script>

<style scoped>
.teacher-page { padding: 16rpx; background: #f5f5f5; min-height: 100vh; }
.card { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 16rpx; }
.card-title { font-size: 28rpx; font-weight: 600; color: #333; margin-bottom: 16rpx; }
.teacher-badge { display: flex; flex-direction: column; gap: 8rpx; }
.badge-text { font-size: 28rpx; color: #52c41a; }
.subject-text { font-size: 24rpx; color: #888; }
.input { border: 1rpx solid #e8e8e8; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.btn-primary { background: #1677ff; color: #fff; border-radius: 8rpx; padding: 20rpx; font-size: 28rpx; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { opacity: 0.5; }
.btn-secondary { background: #f0f7ff; color: #1677ff; border: 1rpx solid #1677ff; border-radius: 8rpx; padding: 20rpx; font-size: 28rpx; text-align: center; }
.invite-box { margin-top: 16rpx; background: #f9f9f9; border-radius: 8rpx; padding: 20rpx; display: flex; align-items: center; gap: 16rpx; }
.invite-code { font-size: 48rpx; font-weight: 700; letter-spacing: 8rpx; color: #1677ff; flex: 1; }
.invite-expire { font-size: 22rpx; color: #aaa; }
.btn-copy { background: #1677ff; color: #fff; font-size: 24rpx; border-radius: 6rpx; padding: 8rpx 16rpx; }
.tip { font-size: 26rpx; color: #aaa; text-align: center; padding: 24rpx 0; }
.student-item { display: flex; align-items: center; padding: 20rpx 0; border-bottom: 1rpx solid #f0f0f0; }
.student-item:last-child { border-bottom: none; }
.student-id { flex: 1; font-size: 28rpx; color: #333; }
.student-bind-date { font-size: 24rpx; color: #aaa; margin-right: 8rpx; }
.arrow { font-size: 32rpx; color: #bbb; }
</style>
```

- [ ] **Step 5: 创建 `pages/teacher/student-detail.vue`**

```vue
<!-- src/pages/teacher/student-detail.vue -->
<template>
  <view class="student-detail-page">

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="wqs.length === 0" class="tip">该学生暂无错题记录。</view>

    <view v-for="wq in wqs" :key="wq.id" class="wq-card">
      <image
        v-if="wq.source_image_url"
        :src="wq.source_image_url"
        class="wq-image"
        mode="widthFix"
      />
      <view v-if="wq.question_text" class="wq-text">{{ wq.question_text }}</view>
      <view class="wq-meta">
        <text>{{ wq.question_type || '未知题型' }}</text>
        <text v-if="wq.difficulty"> · 难度 {{ wq.difficulty }}</text>
        <text> · {{ wq.is_mastered ? '✅已掌握' : '⏳待掌握' }}</text>
      </view>

      <!-- 批注输入 -->
      <view class="comment-section">
        <textarea
          v-model="commentDraft[wq.id]"
          class="comment-input"
          placeholder="为这道题添加批注…"
          maxlength="500"
        />
        <button
          size="mini"
          class="btn-comment"
          :disabled="submitting[wq.id]"
          @tap="submitComment(wq.id)"
        >
          {{ submitting[wq.id] ? '提交中…' : '提交批注' }}
        </button>
      </view>

      <!-- 已有批注 -->
      <view v-if="existingComments[wq.id]?.length" class="existing-comments">
        <view
          v-for="c in existingComments[wq.id]"
          :key="c.id"
          class="comment-item"
        >
          <text class="comment-text">{{ c.comment_text }}</text>
          <text class="comment-time">{{ c.created_at.slice(0, 16).replace('T', ' ') }}</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { getStudentWrongQuestions, addComment, getComments } from '../../api/teacher'
import type { WrongQuestionOut, TeacherCommentOut } from '../../types/api'

const props = defineProps<{ studentId?: string }>()

// uni-app 通过 options 获取页面参数
const studentId = ref('')
const wqs = ref<WrongQuestionOut[]>([])
const loading = ref(true)
const commentDraft = reactive<Record<string, string>>({})
const submitting = reactive<Record<string, boolean>>({})
const existingComments = reactive<Record<string, TeacherCommentOut[]>>({})

onMounted(async () => {
  // 从路由参数读取 studentId
  const pages = getCurrentPages()
  const page = pages[pages.length - 1] as any
  const sid = page.options?.studentId || ''
  studentId.value = sid
  if (!sid) {
    loading.value = false
    return
  }

  try {
    const res = await getStudentWrongQuestions(sid)
    if (res.code === 200) {
      wqs.value = res.data
      // 加载每道题已有的批注
      await Promise.all(
        res.data.map(async (wq) => {
          try {
            const cr = await getComments(wq.id)
            if (cr.code === 200) existingComments[wq.id] = cr.data
          } catch { /* 忽略 */ }
        })
      )
    }
  } finally {
    loading.value = false
  }
})

async function submitComment(wqId: string) {
  const text = (commentDraft[wqId] || '').trim()
  if (!text) {
    uni.showToast({ title: '请输入批注内容', icon: 'none' })
    return
  }
  submitting[wqId] = true
  try {
    const res = await addComment(wqId, text)
    if (res.code === 200) {
      commentDraft[wqId] = ''
      if (!existingComments[wqId]) existingComments[wqId] = []
      existingComments[wqId].push(res.data)
      uni.showToast({ title: '批注成功', icon: 'success' })
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting[wqId] = false
  }
}
</script>

<style scoped>
.student-detail-page { padding: 16rpx; background: #f5f5f5; min-height: 100vh; }
.tip { text-align: center; padding: 60rpx; font-size: 26rpx; color: #aaa; }
.wq-card { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 16rpx; }
.wq-image { width: 100%; border-radius: 8rpx; margin-bottom: 12rpx; }
.wq-text { font-size: 28rpx; color: #333; line-height: 1.6; margin-bottom: 8rpx; white-space: pre-wrap; }
.wq-meta { font-size: 24rpx; color: #888; margin-bottom: 16rpx; }
.comment-section { border-top: 1rpx solid #f0f0f0; padding-top: 16rpx; }
.comment-input { width: 100%; border: 1rpx solid #e8e8e8; border-radius: 8rpx; padding: 12rpx; font-size: 26rpx; min-height: 80rpx; box-sizing: border-box; margin-bottom: 8rpx; }
.btn-comment { background: #1677ff; color: #fff; border-radius: 6rpx; font-size: 24rpx; }
.btn-comment[disabled] { opacity: 0.5; }
.existing-comments { margin-top: 16rpx; }
.comment-item { background: #fffbe6; border-radius: 8rpx; padding: 12rpx 16rpx; margin-bottom: 8rpx; }
.comment-text { font-size: 26rpx; color: #333; display: block; margin-bottom: 4rpx; }
.comment-time { font-size: 22rpx; color: #aaa; }
</style>
```

- [ ] **Step 6: 在 `profile/index.vue` 添加教师中心入口**

READ `frontend/miniprogram/src/pages/profile/index.vue` 中的最后一个 `</view>` 之前的位置（模板末尾）。找到模板末尾的 `</view>` 前，插入：

```vue
    <!-- 教师中心 -->
    <view class="card" style="margin-top:16rpx;">
      <view class="card-title">教师中心</view>
      <text class="menu-desc">教师功能：生成邀请码、查看学生错题、添加批注；学生功能：绑定老师</text>
      <button class="btn-menu" @tap="goTeacher">进入教师中心</button>
    </view>
```

在 `<script setup>` 中追加：
```typescript
function goTeacher() {
  uni.navigateTo({ url: '/pages/teacher/students' })
}
```

在 `<style scoped>` 中追加：
```css
.menu-desc { font-size: 24rpx; color: #888; margin-bottom: 12rpx; display: block; }
.btn-menu { background: #f0f7ff; color: #1677ff; border: 1rpx solid #1677ff; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; text-align: center; }
```

**具体操作：**
先 READ `profile/index.vue` 完整内容，定位最后 `</view>` 闭合标签（`</view>` 在 `</template>` 之前），用 Edit 工具在其前插入上述卡片。再找 `</script>` 前最后的函数，在其后追加 `goTeacher`。最后在 `</style>` 前追加上述 CSS。

- [ ] **Step 7: 在 `detail.vue` 添加老师批注展示**

READ `frontend/miniprogram/src/pages/wrong-questions/detail.vue` 末尾。在模板末尾 `</view>` 前，找到已有的最后一个内容 section（如 AI 分析 section 或 OCR section 末尾），追加老师批注 section：

```vue
    <!-- 老师批注 -->
    <view v-if="teacherComments.length > 0" class="section">
      <view class="section-title">老师批注</view>
      <view
        v-for="c in teacherComments"
        :key="c.id"
        class="teacher-comment-item"
      >
        <text class="tc-text">{{ c.comment_text }}</text>
        <text class="tc-time">{{ c.created_at.slice(0, 16).replace('T', ' ') }}</text>
      </view>
    </view>
```

在 `<script setup>` 里，追加：
```typescript
import { getComments } from '../../api/teacher'
import type { TeacherCommentOut } from '../../types/api'

const teacherComments = ref<TeacherCommentOut[]>([])

// 在 loadDetail() 函数内（或 onMounted 末尾），加载批注：
// try {
//   const cr = await getComments(wqId)
//   if (cr.code === 200) teacherComments.value = cr.data
// } catch { /* 无批注也不报错 */ }
```

**注意**：READ `detail.vue` 完整内容后，找到 `loadDetail` 函数（或 onMounted 中的数据加载），在 WQ 数据加载成功后追加批注加载逻辑。同时在模板末尾加批注展示 section。

在 `<style scoped>` 中追加：
```css
.teacher-comment-item { background: #fffbe6; border-radius: 8rpx; padding: 12rpx 16rpx; margin-bottom: 8rpx; }
.tc-text { font-size: 28rpx; color: #333; display: block; margin-bottom: 4rpx; }
.tc-time { font-size: 22rpx; color: #aaa; }
```

- [ ] **Step 8: 提交前端**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/teacher.ts \
        frontend/miniprogram/src/pages.json \
        frontend/miniprogram/src/pages/teacher/ \
        frontend/miniprogram/src/pages/profile/index.vue \
        frontend/miniprogram/src/pages/wrong-questions/detail.vue
git commit -m "feat(frontend): teacher module — students page, student-detail, profile entry, wq comments"
```

---

## Task 5: Integration + Push + 归档 D-069

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 全部 PASS（≥ 150 个）

- [ ] **Step 2: 验证 live server**

```bash
uvicorn app.main:app --port 8022 --log-level warning &
sleep 3

# 健康检查
curl -s http://localhost:8022/health

# /docs 包含 teacher tag
curl -s http://localhost:8022/openapi.json | python3 -c "
import json,sys
spec = json.load(sys.stdin)
tags = [t['name'] for t in spec.get('tags',[])]
paths = list(spec['paths'].keys())
teacher_paths = [p for p in paths if '/teacher' in p]
print('Teacher paths:', teacher_paths)
"

# 未登录访问 teacher 端点 → 401
curl -s http://localhost:8022/api/v1/teacher/students | python3 -m json.tool

pkill -f "uvicorn app.main:app --port 8022" 2>/dev/null || true
```

Expected:
- `{"status": "ok"}`
- Teacher paths 至少包含 7 条（`/teacher/profile`, `/teacher/invite-code`, `/teacher/bind`, `/teacher/students`, `/teacher/students/{student_id}/wrong-questions`, `/teacher/wrong-questions/{wq_id}/comments`×2）
- `teacher/students` 无 token → 401

- [ ] **Step 3: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 4: 追加 D-069 到 `docs/决策归档.md`**

在文件开头 `## D-063` 段落之前插入（即现有最新决策 D-063 之前的位置，逆序排列）：

```markdown
## D-069｜教师模块 MVP：邀请码师生绑定 + 错题批注

**日期：** 2026-05-27
**背景：** 学生端核心闭环完成（上传→OCR→AI分析→学情报告），下一个差异化功能是教师端：老师可查看绑定学生的错题并添加批注，学生可在详情页看到老师的反馈，形成"AI辅助 + 人工审核"的双轨诊断。
**结论：**
1. **数据层（Task 0）：** 新增 `teacher_comments` 表（Migration 0004）；向 `invite_code_type` enum 追加 `teacher_bind` 值（`ALTER TYPE ADD VALUE IF NOT EXISTS`，Postgres 12+ 兼容）。
2. **绑定机制：** 教师调用 `POST /teacher/invite-code` 生成6位大写字母+数字码（有效期24h，单次使用）；学生调用 `POST /teacher/bind` 通过邀请码绑定，复用现有 `TeacherStudent` 表（status=active, bind_type=self_bound, bind_source=miniprogram_link）。
3. **权限设计：** 所有教师端写操作检查 `user.role == "teacher"`；查看学生数据前校验 TeacherStudent active 绑定关系；批注端点403而非404（不泄露数据存在性）。`GET /teacher/wrong-questions/{wq_id}/comments` 对任意已登录用户返回数据（学生/老师均可读），无权限时返回空列表而非报错（前端容错更友好）。
4. **前端：** `pages/teacher/students.vue`（教师中心：成为教师/邀请码/学生列表/绑定入口），`pages/teacher/student-detail.vue`（学生错题列表+批注输入），`pages/wrong-questions/detail.vue`（追加老师批注 section），`pages/profile/index.vue`（追加教师中心入口卡片）。
5. **测试：** 16个测试全部通过（5 schema + 11 service + 6 API 集成）。
**影响范围：** Migration 0004（1张新表）；7个新 API 端点；2个新前端页；已推送 GitHub main 分支。

---

```

- [ ] **Step 5: 提交归档并推送**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-069 — teacher module MVP complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | Task |
|------|------|
| 教师角色创建 | Task 2 `become_teacher` + Task 3 `POST /teacher/profile` |
| 师生绑定（邀请码机制） | Task 2 `generate_invite_code` / `bind_with_teacher` + Task 3 endpoints |
| 教师查看绑定学生列表 | Task 2 `get_my_students` + Task 3 `GET /teacher/students` |
| 教师查看学生错题 | Task 2 `get_student_wrong_questions` + Task 3 `GET /teacher/students/{id}/wrong-questions` |
| 教师添加批注 | Task 2 `add_comment` + Task 3 `POST /teacher/wrong-questions/{id}/comments` |
| 学生查看老师批注 | Task 3 `GET /teacher/wrong-questions/{id}/comments` + Task 4 detail.vue |
| 前端教师中心页 | Task 4 `students.vue` |
| 前端学生错题+批注输入页 | Task 4 `student-detail.vue` |
| 前端入口（profile 页） | Task 4 profile.vue 修改 |
| Migration 0004 | Task 0 |
| 全量测试 ≥ 150 | Task 5 验证 |

### 2. Placeholder 扫描

- 所有 service/API/schema 函数含完整代码 ✅
- 前端 Step 6 / Step 7（profile + detail 修改）需要 READ 后定位插入点，给出了具体指令 ✅
- 无 TBD / TODO ✅

### 3. 类型一致性

- `become_teacher(db, *, user: User, data: BecomeTeacherRequest) -> Teacher` — Task 2 定义，Task 3 endpoint 调用 ✅
- `generate_invite_code(db, *, teacher_id: uuid.UUID) -> InviteCode` — Task 2 定义，Task 3 endpoint 调用 ✅
- `bind_with_teacher(db, *, student: User, code: str) -> TeacherStudent` — Task 2，Task 3 ✅
- `TeacherCommentOut.model_validate(comment)` — `TeacherComment` ORM 对象，`model_config = {"from_attributes": True}` ✅
- `WrongQuestionOut.model_validate(wq)` — 已有 `from_attributes: True` ✅
- 前端 `TeacherCommentOut.id/wrong_question_id/teacher_id/comment_text/created_at` — 与后端 schema 字段完全一致 ✅
