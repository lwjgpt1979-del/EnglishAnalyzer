# Alembic Initial Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零搭建 FastAPI 后端 Python 项目，为全部 37 张表编写 SQLAlchemy 2.x 模型（含 G14-G22 修复，定版 v3.1），并生成可对空白 PostgreSQL 数据库直接执行的 Alembic 初始建表迁移脚本。

**Architecture:** Shared-schema 多租户 PostgreSQL 数据库，UUID 主键、TIMESTAMPTZ 时间戳、PostgreSQL 原生 ENUM、JSONB、ARRAY、部分唯一索引。模型按 10 个域拆分为独立文件，与 Tech Spec 结构一一对应。RLS 策略与种子数据不在本次范围内（留给后续 migration）。

**Tech Stack:** Python 3.12 · FastAPI 0.115+ · SQLAlchemy 2.x (mapped_column 风格) · Alembic 1.14+ · psycopg[binary] 3.x (同步，供 Alembic 使用) · pytest 8+

---

## 文件结构

```
backend/
├── pyproject.toml                        # 依赖声明
├── .env.example                          # 环境变量模板
├── alembic.ini                           # Alembic 配置
├── alembic/
│   ├── env.py                            # Alembic 运行环境（导入所有模型）
│   ├── script.py.mako                    # 迁移脚本模板
│   └── versions/
│       └── 0001_initial_schema.py        # 手写初始建表迁移（autogenerate 生成后调整）
└── app/
    ├── __init__.py
    ├── core/
    │   ├── __init__.py
    │   └── database.py                   # engine + SessionLocal
    └── models/
        ├── __init__.py                   # 统一导入，暴露 Base.metadata
        ├── base.py                       # DeclarativeBase
        ├── d1_users.py                   # 域1: 8 张表
        ├── d2_payments.py                # 域2: 3 张表
        ├── d3_wrong_questions.py         # 域3: 3 张表
        ├── d4_knowledge.py               # 域4: 5 张表
        ├── d5_learning.py                # 域5: 5 张表
        ├── d6_ai_questions.py            # 域6: 2 张表
        ├── d7_teacher.py                 # 域7: 4 张表
        ├── d8_usage.py                   # 域8: 2 张表
        ├── d9_system.py                  # 域9: 2 张表
        └── d10_branch.py                 # 域10: 3 张表

tests/
├── __init__.py
└── models/
    ├── __init__.py
    └── test_model_structure.py           # 无需 DB 的模型结构测试
```

---

### Task 0: 应用 G14-G22，Tech Spec 定版 v3.1

**Files:**
- Modify: `docs/superpowers/specs/2026-05-24-tech-spec-design.md`
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 在 Tech Spec 中搜索 `vocabulary_learning` 表定义，添加 `created_at` 字段 (G14)**

找到 `vocabulary_learning` 表定义，在 `level ENUM(new/learning/review/mastered)` 之后添加：
```
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

- [ ] **Step 2: 在 Tech Spec 中找到 `notifications` 表定义，添加 `read_at` 字段 (G15)**

在 `is_read BOOLEAN DEFAULT false` 之后添加：
```
read_at TIMESTAMPTZ (nullable)
```

- [ ] **Step 3: 在 Tech Spec 中找到 `branch_company_cities` 表定义，添加 `created_at` 字段 (G16)**

在 `effective_to DATE (nullable)` 之后添加：
```
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

- [ ] **Step 4: 在 Tech Spec 中找到 `teacher_students.status` 枚举，补充 `inactive` 值 (G17)**

将：
```
status ENUM(pending/active/rejected)
```
改为：
```
status ENUM(pending/active/rejected/inactive)
```
并在表注释中添加：`unbound_at 有值时 status→inactive；UNIQUE WHERE status='active' 允许重新绑定`

- [ ] **Step 5: 在 Tech Spec 中找到 `branch_settlements` 表定义，添加 `updated_at` 字段 (G18)**

在 `created_at TIMESTAMPTZ` 之前添加：
```
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

- [ ] **Step 6: 在 Tech Spec 中找到 `memberships` 表定义，添加 `order_id` 字段 (G19)**

在 `user_id UUID FK → users` 之后添加：
```
order_id UUID FK → orders (nullable)
```

- [ ] **Step 7: 在 Tech Spec 中找到 `ai_questions` 表定义，添加 `updated_at` 字段 (G20)**

在 `usage_count INT DEFAULT 0` 之后添加：
```
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

- [ ] **Step 8: 在 Tech Spec 中找到 `assignments` 表定义，添加 `published_at` 字段 (G21)**

在 `status ENUM(draft/published/closed)` 之后添加：
```
published_at TIMESTAMPTZ (nullable)
```

- [ ] **Step 9: 在 Tech Spec 中找到 `refund_records` 表定义，添加 `reviewed_by` 字段 (G22)**

在 `branch_company_id UUID FK → branch_companies (nullable)` 之后添加：
```
reviewed_by UUID FK → users (nullable)
```

- [ ] **Step 10: 将 Tech Spec 版本号从 v3.0 改为 v3.1，更新修订历史**

在文档顶部或修订历史区域添加：
```
v3.1 (2026-05-25) — 应用 G14-G22，定版 37 张表
```

- [ ] **Step 11: 在 `docs/决策归档.md` 顶部追加 D-058（倒序，新条目在最前面）**

```markdown
## D-058｜Tech Spec v3.0→v3.1：应用 G14-G22 九项补全

**日期：** 2026-05-25
**背景：** 第16-19轮 Section3 回归共发现 G14-G22 九个字段/枚举缺失，推迟批量修入。
**结论：** 一次性应用全部九项修复，Tech Spec 从 v3.0 升级至 v3.1 定版；G14 vocabulary_learning 补 created_at，G15 notifications 补 read_at，G16 branch_company_cities 补 created_at，G17 teacher_students.status 补 inactive，G18 branch_settlements 补 updated_at，G19 memberships 补 order_id FK，G20 ai_questions 补 updated_at，G21 assignments 补 published_at，G22 refund_records 补 reviewed_by FK。
**影响范围：** Tech Spec Section3 全部 37 张表定版；后续 Alembic 建表脚本直接基于 v3.1 编写。
```

- [ ] **Step 12: Commit**

```bash
git add docs/superpowers/specs/2026-05-24-tech-spec-design.md docs/决策归档.md
git commit -m "spec(section3): apply G14-G22, bump to v3.1, archive D-058"
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/models/__init__.py` (空文件，Task 11 再填充)
- Create: `tests/__init__.py`
- Create: `tests/models/__init__.py`

- [ ] **Step 1: 写失败测试——验证依赖可导入**

Create `tests/models/test_model_structure.py`：
```python
"""
Model structure tests — no live database required.
Tests run by importing models and inspecting SQLAlchemy Table objects.
"""
import pytest


def test_sqlalchemy_importable():
    import sqlalchemy as sa
    assert sa.__version__.startswith("2.")


def test_alembic_importable():
    import alembic
    assert alembic.__version__ >= "1.13"
```

- [ ] **Step 2: 运行测试，确认失败（依赖未安装）**

```bash
cd backend
python -m pytest ../tests/models/test_model_structure.py::test_sqlalchemy_importable -v
```

Expected: `ModuleNotFoundError: No module named 'sqlalchemy'`

- [ ] **Step 3: 创建 `backend/pyproject.toml`**

```toml
[project]
name = "enggramer-backend"
version = "0.1.0"
description = "engGramer SaaS — FastAPI backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14.0",
    "psycopg[binary]>=3.1.0",
    "pydantic-settings>=2.3.0",
    "python-dotenv>=1.0.1",
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
```

- [ ] **Step 4: 创建 `backend/.env.example`**

```dotenv
# PostgreSQL 连接（迁移用同步连接）
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/enggramer

# 异步连接（FastAPI 应用使用，Alembic 不用）
ASYNC_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/enggramer
```

- [ ] **Step 5: 安装依赖**

```bash
cd backend
pip install -e ".[dev]"
```

Expected: 所有包安装成功，无 error。

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend
python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `2 passed`

- [ ] **Step 7: 创建空白 __init__.py 文件**

```bash
touch backend/app/__init__.py
touch backend/app/core/__init__.py
touch backend/app/models/__init__.py
touch tests/__init__.py
touch tests/models/__init__.py
```

- [ ] **Step 8: Commit**

```bash
git add backend/ tests/
git commit -m "chore: scaffold backend project with pyproject.toml + pytest"
```

---

### Task 2: SQLAlchemy Base + Database 配置

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/core/database.py`
- Test: `tests/models/test_model_structure.py`

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_base_importable():
    from app.models.base import Base
    import sqlalchemy as sa
    # Base.metadata 是 SQLAlchemy MetaData 对象
    assert isinstance(Base.metadata, sa.MetaData)


def test_database_engine_config():
    from app.core.database import get_engine_url
    # 读取 DATABASE_URL 环境变量（未设置时返回 None 而不崩溃）
    url = get_engine_url()
    assert url is None or url.startswith("postgresql")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_base_importable -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: 创建 `backend/app/models/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 SQLAlchemy 模型的基类。"""
    pass
```

- [ ] **Step 4: 创建 `backend/app/core/database.py`**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_engine_url() -> str | None:
    """从环境变量读取数据库 URL（不存在则返回 None）。"""
    return os.getenv("DATABASE_URL")


def create_sync_engine(url: str | None = None):
    """创建同步 SQLAlchemy engine（供 Alembic 迁移使用）。"""
    db_url = url or get_engine_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_engine(db_url, echo=False)


def create_session_factory(engine):
    """返回 SessionLocal 工厂。"""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/base.py backend/app/core/database.py tests/models/test_model_structure.py
git commit -m "feat: add SQLAlchemy DeclarativeBase + database engine config"
```

---

### Task 3: 域1 模型 — Users & Tenants（8 张表）

**Files:**
- Create: `backend/app/models/d1_users.py`
- Test: `tests/models/test_model_structure.py`

**表：** users · institutions · students · teachers · relatives · student_relatives · teacher_students · invite_codes

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d1_users_tables():
    from app.models.d1_users import (
        User, Institution, Student, Teacher,
        Relative, StudentRelative, TeacherStudent, InviteCode,
    )
    assert User.__tablename__ == "users"
    assert Institution.__tablename__ == "institutions"
    assert Student.__tablename__ == "students"
    assert Teacher.__tablename__ == "teachers"
    assert Relative.__tablename__ == "relatives"
    assert StudentRelative.__tablename__ == "student_relatives"
    assert TeacherStudent.__tablename__ == "teacher_students"
    assert InviteCode.__tablename__ == "invite_codes"


def test_user_columns():
    from app.models.d1_users import User
    cols = {c.name for c in User.__table__.columns}
    required = {
        "id", "openid", "phone", "nickname", "avatar_url",
        "role", "is_active", "city_code", "city_source",
        "ip_at_registration", "created_at", "updated_at",
    }
    assert required <= cols, f"缺失字段: {required - cols}"


def test_teacher_student_status_has_inactive():
    """G17: teacher_students.status 必须包含 inactive。"""
    from app.models.d1_users import TeacherStudent
    status_col = TeacherStudent.__table__.c["status"]
    enum_values = set(status_col.type.enums)
    assert "inactive" in enum_values, "G17 修复未应用: 缺少 inactive"


def test_teacher_students_partial_unique_index():
    from app.models.d1_users import TeacherStudent
    indexes = TeacherStudent.__table__.indexes
    partial = [i for i in indexes if i.unique and "active" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))]
    assert len(partial) == 1, "缺少 UNIQUE WHERE status='active' 部分唯一索引"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d1_users_tables -v
```

Expected: `ModuleNotFoundError: No module named 'app.models.d1_users'`

- [ ] **Step 3: 创建 `backend/app/models/d1_users.py`**

```python
"""
域1: 用户与租户 (8 张表)
  users · institutions · students · teachers · relatives ·
  student_relatives · teacher_students · invite_codes
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

user_role_enum = sa.Enum(
    "student", "teacher", "relative",
    "institution_admin", "branch_admin", "platform_admin",
    name="user_role",
)
city_source_enum = sa.Enum(
    "ip_auto", "manual",
    name="city_source",
)
institution_status_enum = sa.Enum(
    "pending", "active", "suspended",
    name="institution_status",
)
semester_enum = sa.Enum("上", "下", name="semester")

cert_status_enum = sa.Enum(
    "uncertified", "pending", "certified", "rejected",
    name="cert_status",
)
bind_type_enum = sa.Enum(
    "institution_assigned", "self_bound",
    name="bind_type",
)
bind_source_enum = sa.Enum(
    "sms_invite", "miniprogram_link", "institution_assigned",
    name="bind_source",
)
# G17: 补充 inactive（unbound_at 有值时 status→inactive）
teacher_student_status_enum = sa.Enum(
    "pending", "active", "rejected", "inactive",
    name="teacher_student_status",
)
invite_code_type_enum = sa.Enum(
    "relative_bind", "institution_join",
    name="invite_code_type",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    openid = mapped_column(sa.String, nullable=False, unique=True)
    phone = mapped_column(sa.String, nullable=True)
    nickname = mapped_column(sa.String, nullable=True)
    avatar_url = mapped_column(sa.String, nullable=True)
    role = mapped_column(user_role_enum, nullable=False)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    city_code = mapped_column(sa.String, nullable=True)
    city_source = mapped_column(city_source_enum, nullable=True)
    ip_at_registration = mapped_column(INET, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Institution(Base):
    __tablename__ = "institutions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String, nullable=False)
    contact_phone = mapped_column(sa.String, nullable=False)
    commission_rate = mapped_column(sa.Numeric(5, 4), nullable=True)
    province_code = mapped_column(sa.String, nullable=False)
    city_code = mapped_column(sa.String, nullable=False)
    address = mapped_column(sa.String, nullable=False)
    status = mapped_column(
        institution_status_enum,
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Student(Base):
    """学生扩展信息表（PK 同时是 users.id 的 FK）。"""

    __tablename__ = "students"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    grade = mapped_column(sa.String, nullable=True)
    textbook_ver = mapped_column(sa.String, nullable=True)
    semester = mapped_column(semester_enum, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Teacher(Base):
    """教师扩展信息表。"""

    __tablename__ = "teachers"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    cert_status = mapped_column(
        cert_status_enum,
        nullable=False,
        server_default=sa.text("'uncertified'"),
    )
    cert_doc_url = mapped_column(sa.String, nullable=True)
    subject = mapped_column(sa.String, nullable=True)
    max_students = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("50")
    )
    enterprise_userid = mapped_column(sa.String, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Relative(Base):
    """家长扩展信息表（仅做角色标记，无额外字段）。"""

    __tablename__ = "relatives"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )


class StudentRelative(Base):
    """学生-家长绑定关系（最多 4 个家长，service 层校验）。"""

    __tablename__ = "student_relatives"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    relative_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    relationship = mapped_column(sa.String, nullable=False)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    bound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    unbound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)


class TeacherStudent(Base):
    """师生绑定关系。status=inactive 表示已解绑（unbound_at 有值）。"""

    __tablename__ = "teacher_students"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    bind_type = mapped_column(bind_type_enum, nullable=False)
    bind_source = mapped_column(bind_source_enum, nullable=False)
    status = mapped_column(teacher_student_status_enum, nullable=False)
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    requested_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    bound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    unbound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        # 每对师生同一时刻只能有一条 active 记录；允许重新绑定
        sa.Index(
            "uix_teacher_students_active",
            "teacher_id",
            "student_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String(6), nullable=False, unique=True)
    type = mapped_column(invite_code_type_enum, nullable=False)
    issuer_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    target_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    used_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d1_users.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain1 user & tenant models (8 tables)"
```

---

### Task 4: 域2 模型 — Memberships & Payments（3 张表）

**Files:**
- Create: `backend/app/models/d2_payments.py`
- Test: `tests/models/test_model_structure.py`

**表：** memberships · orders · refund_records

> ⚠️ `memberships.order_id → orders` (G19)：`memberships` 在 `orders` 之后创建，无循环依赖。  
> ⚠️ `orders.branch_company_id → branch_companies`，`refund_records.branch_company_id → branch_companies`：`branch_companies` 表在域10，FK 用字符串引用（SQLAlchemy 解析在所有模型导入后进行）。

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d2_payment_tables():
    from app.models.d2_payments import Membership, Order, RefundRecord
    assert Membership.__tablename__ == "memberships"
    assert Order.__tablename__ == "orders"
    assert RefundRecord.__tablename__ == "refund_records"


def test_membership_has_order_id():
    """G19: memberships 必须有 order_id 字段。"""
    from app.models.d2_payments import Membership
    cols = {c.name for c in Membership.__table__.columns}
    assert "order_id" in cols, "G19 修复未应用: memberships 缺少 order_id"


def test_memberships_partial_unique_index():
    from app.models.d2_payments import Membership
    indexes = Membership.__table__.indexes
    partial = [
        i for i in indexes
        if i.unique and "is_active" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))
    ]
    assert len(partial) == 1, "缺少 UNIQUE WHERE is_active=true 部分唯一索引"


def test_refund_record_has_reviewed_by():
    """G22: refund_records 必须有 reviewed_by 字段。"""
    from app.models.d2_payments import RefundRecord
    cols = {c.name for c in RefundRecord.__table__.columns}
    assert "reviewed_by" in cols, "G22 修复未应用: refund_records 缺少 reviewed_by"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d2_payment_tables -v
```

Expected: `ModuleNotFoundError: No module named 'app.models.d2_payments'`

- [ ] **Step 3: 创建 `backend/app/models/d2_payments.py`**

```python
"""
域2: 会员与支付 (3 张表)
  memberships · orders · refund_records
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

membership_tier_enum = sa.Enum(
    "free", "basic", "pro", "promax",
    name="membership_tier",
)
# orders 的 tier 不含 free（仅付费档）
order_tier_enum = sa.Enum(
    "basic", "pro", "promax",
    name="order_tier",
)
order_type_enum = sa.Enum(
    "new", "renew", "upgrade",
    name="order_type",
)
order_status_enum = sa.Enum(
    "pending", "paid", "refunded", "partial_refunded",
    name="order_status",
)
refund_type_enum = sa.Enum(
    "standard_7d", "prorated", "appeal",
    name="refund_type",
)
refund_status_enum = sa.Enum(
    "pending", "approved", "rejected", "completed",
    name="refund_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class Order(Base):
    """先建 Order，Membership 的 order_id FK 才能引用它。"""

    __tablename__ = "orders"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_no = mapped_column(sa.String, nullable=False, unique=True)
    payer_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    beneficiary_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    order_type = mapped_column(order_type_enum, nullable=False)
    tier = mapped_column(order_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    amount_fen = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(order_status_enum, nullable=False)
    wx_transaction_id = mapped_column(sa.String, nullable=True)
    paid_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    # branch_companies 在域10定义，字符串 FK 由 SQLAlchemy 延迟解析
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    platform_income_fen = mapped_column(sa.Integer, nullable=True)
    branch_commission_fen = mapped_column(sa.Integer, nullable=True)
    institution_commission_fen = mapped_column(sa.Integer, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Membership(Base):
    """
    会员记录。每个用户同时只有一条 is_active=true 的记录（部分唯一索引保证）。
    order_id (G19): 关联触发本次会员的订单，用于幂等校验与审计。
    """

    __tablename__ = "memberships"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    # G19: 关联触发订单，nullable 允许历史数据或免费会员
    order_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    started_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )

    __table_args__ = (
        sa.Index(
            "uix_memberships_user_active",
            "user_id",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )


class RefundRecord(Base):
    __tablename__ = "refund_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False
    )
    amount_fen = mapped_column(sa.Integer, nullable=False)
    refund_type = mapped_column(refund_type_enum, nullable=False)
    status = mapped_column(refund_status_enum, nullable=False)
    reason = mapped_column(sa.Text, nullable=True)
    wx_refund_id = mapped_column(sa.String, nullable=True)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    # G22: 审核人，platform_admin 操作退款审核时填写
    reviewed_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
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

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d2_payments.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain2 payment models (3 tables, G19/G22 applied)"
```

---

### Task 5: 域3 模型 — Wrong Questions & AI Analysis（3 张表）

**Files:**
- Create: `backend/app/models/d3_wrong_questions.py`
- Test: `tests/models/test_model_structure.py`

**表：** wrong_questions · ocr_tasks · ai_analyses

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d3_wrong_question_tables():
    from app.models.d3_wrong_questions import (
        WrongQuestion, OcrTask, AiAnalysis,
    )
    assert WrongQuestion.__tablename__ == "wrong_questions"
    assert OcrTask.__tablename__ == "ocr_tasks"
    assert AiAnalysis.__tablename__ == "ai_analyses"


def test_wrong_question_columns():
    from app.models.d3_wrong_questions import WrongQuestion
    cols = {c.name for c in WrongQuestion.__table__.columns}
    required = {
        "id", "student_id", "institution_id", "source_image_url",
        "question_text", "student_answer", "correct_answer",
        "question_type", "difficulty", "tags", "is_mastered",
        "mastered_at", "updated_at", "created_at",
    }
    assert required <= cols, f"缺失: {required - cols}"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d3_wrong_question_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d3_wrong_questions.py`**

```python
"""
域3: 错题与 AI 诊断 (3 张表)
  wrong_questions · ocr_tasks · ai_analyses
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

question_type_enum = sa.Enum(
    "单选", "完型", "阅读", "作文", "其他",
    name="question_type",
)
ocr_status_enum = sa.Enum(
    "pending", "processing", "completed", "failed",
    name="ocr_status",
)
ocr_provider_enum = sa.Enum(
    "aliyun_print", "baidu_print", "tencent_handwrite", "google_handwrite",
    name="ocr_provider",
)
llm_provider_enum = sa.Enum(
    "deepseek", "claude",
    name="llm_provider",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    source_image_url = mapped_column(sa.String, nullable=False)
    question_text = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    question_type = mapped_column(question_type_enum, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=True)
    tags = mapped_column(JSONB, nullable=True)
    is_mastered = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    mastered_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class OcrTask(Base):
    """OCR 任务（4层流水线状态跟踪）。"""

    __tablename__ = "ocr_tasks"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    status = mapped_column(ocr_status_enum, nullable=False)
    provider = mapped_column(ocr_provider_enum, nullable=True)
    raw_result = mapped_column(JSONB, nullable=True)
    error_message = mapped_column(sa.Text, nullable=True)
    retry_count = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    completed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)


class AiAnalysis(Base):
    """AI 诊断结果（每次分析生成一条，不可更新）。"""

    __tablename__ = "ai_analyses"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    llm_provider = mapped_column(llm_provider_enum, nullable=False)
    error_types = mapped_column(JSONB, nullable=False)
    knowledge_points = mapped_column(JSONB, nullable=False)
    diagnosis = mapped_column(sa.Text, nullable=False)
    suggestions = mapped_column(sa.Text, nullable=False)
    confidence_score = mapped_column(sa.Numeric(4, 3), nullable=True)
    tokens_used = mapped_column(sa.Integer, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d3_wrong_questions.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain3 wrong question & AI analysis models (3 tables)"
```

---

### Task 6: 域4 模型 — Knowledge System（5 张表）

**Files:**
- Create: `backend/app/models/d4_knowledge.py`
- Test: `tests/models/test_model_structure.py`

**表：** knowledge_points · curriculum_units · unit_knowledge_points · curriculum_words · wrong_question_knowledge_points

> ⚠️ `knowledge_points.parent_id` 是自引用 FK，SQLAlchemy 正常处理。  
> ⚠️ `curriculum_words.word_id → vocabulary_words`（域5）：字符串 FK，所有模型导入后才解析。

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d4_knowledge_tables():
    from app.models.d4_knowledge import (
        KnowledgePoint, CurriculumUnit, UnitKnowledgePoint,
        CurriculumWord, WrongQuestionKnowledgePoint,
    )
    assert KnowledgePoint.__tablename__ == "knowledge_points"
    assert CurriculumUnit.__tablename__ == "curriculum_units"
    assert UnitKnowledgePoint.__tablename__ == "unit_knowledge_points"
    assert CurriculumWord.__tablename__ == "curriculum_words"
    assert WrongQuestionKnowledgePoint.__tablename__ == "wrong_question_knowledge_points"


def test_knowledge_point_self_fk():
    from app.models.d4_knowledge import KnowledgePoint
    cols = {c.name for c in KnowledgePoint.__table__.columns}
    assert "parent_id" in cols, "knowledge_points 缺少 parent_id 自引用 FK"
    assert "applicable_grades" in cols
    assert "applicable_textbooks" in cols


def test_curriculum_unit_unique_constraint():
    from app.models.d4_knowledge import CurriculumUnit
    unique_constraints = [
        c for c in CurriculumUnit.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) > 1
    ]
    assert len(unique_constraints) >= 1, "curriculum_units 缺少复合唯一约束"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d4_knowledge_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d4_knowledge.py`**

```python
"""
域4: 知识体系 (5 张表)
  knowledge_points · curriculum_units · unit_knowledge_points ·
  curriculum_words · wrong_question_knowledge_points
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

knowledge_category_enum = sa.Enum(
    "grammar", "vocabulary", "reading", "writing", "listening",
    name="knowledge_category",
)
# semester_enum 在 d1_users.py 已定义；Alembic 迁移中同名 ENUM 共享
# 这里从 d1_users 直接 import 避免重复创建
from .d1_users import semester_enum  # noqa: E402

# ─── MODELS ──────────────────────────────────────────────────────────────────


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String, nullable=False, unique=True)
    name = mapped_column(sa.String, nullable=False)
    category = mapped_column(knowledge_category_enum, nullable=False)
    description = mapped_column(sa.Text, nullable=True)
    # PostgreSQL TEXT[]
    applicable_grades = mapped_column(ARRAY(sa.String), nullable=False)
    applicable_textbooks = mapped_column(ARRAY(sa.String), nullable=False)
    # 自引用 FK（树形知识点结构）
    parent_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        nullable=True,
    )
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))


class CurriculumUnit(Base):
    __tablename__ = "curriculum_units"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    unit_no = mapped_column(sa.Integer, nullable=False)
    unit_title = mapped_column(sa.String, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "textbook_version", "grade", "semester", "unit_no",
            name="uix_curriculum_units_identity",
        ),
    )


class UnitKnowledgePoint(Base):
    """课单元与知识点多对多（复合 PK）。"""

    __tablename__ = "unit_knowledge_points"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )


class CurriculumWord(Base):
    """课单元词汇表（word_id → vocabulary_words，域5，字符串 FK）。"""

    __tablename__ = "curriculum_words"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    word_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("vocabulary_words.id"),  # 域5，延迟解析
        primary_key=True,
    )
    is_core = mapped_column(sa.Boolean, nullable=False)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))


class WrongQuestionKnowledgePoint(Base):
    """错题与知识点多对多（AI 诊断结果关联）。"""

    __tablename__ = "wrong_question_knowledge_points"

    wrong_question_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("wrong_questions.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `17 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d4_knowledge.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain4 knowledge system models (5 tables)"
```

---

### Task 7: 域5 模型 — Learning Features（5 张表）

**Files:**
- Create: `backend/app/models/d5_learning.py`
- Test: `tests/models/test_model_structure.py`

**表：** vocabulary_words · vocabulary_learning · essays · listening_records · study_checkins

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d5_learning_tables():
    from app.models.d5_learning import (
        VocabularyWord, VocabularyLearning, Essay,
        ListeningRecord, StudyCheckin,
    )
    assert VocabularyWord.__tablename__ == "vocabulary_words"
    assert VocabularyLearning.__tablename__ == "vocabulary_learning"
    assert Essay.__tablename__ == "essays"
    assert ListeningRecord.__tablename__ == "listening_records"
    assert StudyCheckin.__tablename__ == "study_checkins"


def test_vocabulary_learning_has_created_at():
    """G14: vocabulary_learning 必须有 created_at 字段。"""
    from app.models.d5_learning import VocabularyLearning
    cols = {c.name for c in VocabularyLearning.__table__.columns}
    assert "created_at" in cols, "G14 修复未应用: vocabulary_learning 缺少 created_at"


def test_vocabulary_learning_unique_constraint():
    from app.models.d5_learning import VocabularyLearning
    unique_constraints = [
        c for c in VocabularyLearning.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "vocabulary_learning 缺少 (student_id, word_id) 唯一约束"


def test_study_checkin_unique_constraint():
    from app.models.d5_learning import StudyCheckin
    unique_constraints = [
        c for c in StudyCheckin.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "study_checkins 缺少 (student_id, checkin_date) 唯一约束"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d5_learning_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d5_learning.py`**

```python
"""
域5: 学习功能 (5 张表)
  vocabulary_words · vocabulary_learning · essays ·
  listening_records · study_checkins
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

vocab_level_enum = sa.Enum(
    "new", "learning", "review", "mastered",
    name="vocab_level",
)
essay_status_enum = sa.Enum(
    "draft", "processing", "completed",
    name="essay_status",
)
listening_status_enum = sa.Enum(
    "processing", "completed", "failed",
    name="listening_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class VocabularyWord(Base):
    """单词词典（全局共享，不绑定学生）。"""

    __tablename__ = "vocabulary_words"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word = mapped_column(sa.String, nullable=False)
    phonetic = mapped_column(sa.String, nullable=True)
    definitions = mapped_column(JSONB, nullable=False)
    examples = mapped_column(JSONB, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=False)  # 1-5


class VocabularyLearning(Base):
    """
    学生单词学习记录（SM-2 算法状态）。
    G14: 补充 created_at。
    """

    __tablename__ = "vocabulary_learning"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), nullable=False
    )
    interval_days = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    repetitions = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    easiness_factor = mapped_column(
        sa.Numeric(4, 2), nullable=False, server_default=sa.text("2.5")
    )
    next_review_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    last_reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    level = mapped_column(vocab_level_enum, nullable=False)
    # G14: 补充 created_at
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "word_id",
            name="uix_vocabulary_learning_student_word",
        ),
    )


class Essay(Base):
    """学生作文润色记录（可多轮）。"""

    __tablename__ = "essays"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True
    )
    original_text = mapped_column(sa.Text, nullable=False)
    polished_text = mapped_column(sa.Text, nullable=True)
    dimensions = mapped_column(JSONB, nullable=True)
    round_count = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("1")
    )
    status = mapped_column(essay_status_enum, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class ListeningRecord(Base):
    """听力口语练习记录。"""

    __tablename__ = "listening_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    audio_url = mapped_column(sa.String, nullable=False)
    reference_url = mapped_column(sa.String, nullable=False)
    status = mapped_column(listening_status_enum, nullable=False)
    score = mapped_column(sa.Numeric(5, 2), nullable=True)
    feedback = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class StudyCheckin(Base):
    """每日学习打卡（每生每天唯一）。"""

    __tablename__ = "study_checkins"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    checkin_date = mapped_column(sa.Date, nullable=False)
    new_words_count = mapped_column(sa.Integer, nullable=False)
    review_done = mapped_column(sa.Boolean, nullable=False)
    streak_days = mapped_column(sa.Integer, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "checkin_date",
            name="uix_study_checkins_student_date",
        ),
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `21 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d5_learning.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain5 learning feature models (5 tables, G14 applied)"
```

---

### Task 8: 域6 模型 — AI Question Bank（2 张表）

**Files:**
- Create: `backend/app/models/d6_ai_questions.py`
- Test: `tests/models/test_model_structure.py`

**表：** ai_questions · practice_records

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d6_ai_question_tables():
    from app.models.d6_ai_questions import AiQuestion, PracticeRecord
    assert AiQuestion.__tablename__ == "ai_questions"
    assert PracticeRecord.__tablename__ == "practice_records"


def test_ai_question_has_updated_at():
    """G20: ai_questions 必须有 updated_at 字段。"""
    from app.models.d6_ai_questions import AiQuestion
    cols = {c.name for c in AiQuestion.__table__.columns}
    assert "updated_at" in cols, "G20 修复未应用: ai_questions 缺少 updated_at"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d6_ai_question_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d6_ai_questions.py`**

```python
"""
域6: AI 题库与练习 (2 张表)
  ai_questions · practice_records
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

ai_question_type_enum = sa.Enum(
    "单选", "填空", "完型", "阅读", "写作",
    name="ai_question_type",
)
trigger_type_enum = sa.Enum(
    "module8_free", "wrong_q_followup",
    name="trigger_type",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class AiQuestion(Base):
    """AI 生成的练习题（绑定知识点，可关联课单元）。"""

    __tablename__ = "ai_questions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False
    )
    unit_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("curriculum_units.id"), nullable=True
    )
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    difficulty = mapped_column(sa.SmallInteger, nullable=False)  # 1-5
    content = mapped_column(JSONB, nullable=False)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    generated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    usage_count = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    # G20: 补充 updated_at
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class PracticeRecord(Base):
    """学生做题记录。"""

    __tablename__ = "practice_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("ai_questions.id"), nullable=False
    )
    trigger_type = mapped_column(trigger_type_enum, nullable=False)
    student_answer = mapped_column(JSONB, nullable=False)
    is_correct = mapped_column(sa.Boolean, nullable=False)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True
    )
    practiced_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    time_spent_sec = mapped_column(sa.Integer, nullable=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `23 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d6_ai_questions.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain6 AI question bank models (2 tables, G20 applied)"
```

---

### Task 9: 域7 模型 — Teacher Side（4 张表）

**Files:**
- Create: `backend/app/models/d7_teacher.py`
- Test: `tests/models/test_model_structure.py`

**表：** classes · class_students · assignments · assignment_submissions

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d7_teacher_tables():
    from app.models.d7_teacher import (
        Class, ClassStudent, Assignment, AssignmentSubmission,
    )
    assert Class.__tablename__ == "classes"
    assert ClassStudent.__tablename__ == "class_students"
    assert Assignment.__tablename__ == "assignments"
    assert AssignmentSubmission.__tablename__ == "assignment_submissions"


def test_assignment_has_published_at():
    """G21: assignments 必须有 published_at 字段。"""
    from app.models.d7_teacher import Assignment
    cols = {c.name for c in Assignment.__table__.columns}
    assert "published_at" in cols, "G21 修复未应用: assignments 缺少 published_at"


def test_assignment_submission_unique_constraint():
    from app.models.d7_teacher import AssignmentSubmission
    unique_constraints = [
        c for c in AssignmentSubmission.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "assignment_submissions 缺少复合唯一约束"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d7_teacher_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d7_teacher.py`**

```python
"""
域7: 老师端 (4 张表)
  classes · class_students · assignments · assignment_submissions
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

assignment_status_enum = sa.Enum(
    "draft", "published", "closed",
    name="assignment_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class Class(Base):
    __tablename__ = "classes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    name = mapped_column(sa.String, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class ClassStudent(Base):
    """班级-学生多对多（复合 PK）。"""

    __tablename__ = "class_students"

    class_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("classes.id"), primary_key=True
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    joined_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)


class Assignment(Base):
    """作业（可不绑定班级，teacher 直接发布给个别学生时 class_id 为 null）。"""

    __tablename__ = "assignments"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    class_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True
    )
    title = mapped_column(sa.String, nullable=False)
    questions = mapped_column(JSONB, nullable=True)
    due_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    status = mapped_column(assignment_status_enum, nullable=False)
    # G21: status→published 时写入此字段，便于统计发布延迟
    published_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class AssignmentSubmission(Base):
    """学生作业提交（每生每作业唯一）。"""

    __tablename__ = "assignment_submissions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assignments.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    answers = mapped_column(JSONB, nullable=False)
    score = mapped_column(sa.Numeric(5, 2), nullable=True)
    submitted_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "assignment_id", "student_id",
            name="uix_assignment_submissions_unique",
        ),
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `26 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/d7_teacher.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain7 teacher-side models (4 tables, G21 applied)"
```

---

### Task 10: 域8-10 模型 — Usage + System + Branch（7 张表）

**Files:**
- Create: `backend/app/models/d8_usage.py`
- Create: `backend/app/models/d9_system.py`
- Create: `backend/app/models/d10_branch.py`
- Test: `tests/models/test_model_structure.py`

**表：** daily_usage · learning_report_snapshots · system_configs · notifications · branch_companies · branch_company_cities · branch_settlements

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_d8_usage_tables():
    from app.models.d8_usage import DailyUsage, LearningReportSnapshot
    assert DailyUsage.__tablename__ == "daily_usage"
    assert LearningReportSnapshot.__tablename__ == "learning_report_snapshots"


def test_d9_system_tables():
    from app.models.d9_system import SystemConfig, Notification
    assert SystemConfig.__tablename__ == "system_configs"
    assert Notification.__tablename__ == "notifications"


def test_notification_has_read_at():
    """G15: notifications 必须有 read_at 字段。"""
    from app.models.d9_system import Notification
    cols = {c.name for c in Notification.__table__.columns}
    assert "read_at" in cols, "G15 修复未应用: notifications 缺少 read_at"


def test_d10_branch_tables():
    from app.models.d10_branch import (
        BranchCompany, BranchCompanyCity, BranchSettlement,
    )
    assert BranchCompany.__tablename__ == "branch_companies"
    assert BranchCompanyCity.__tablename__ == "branch_company_cities"
    assert BranchSettlement.__tablename__ == "branch_settlements"


def test_branch_company_city_has_created_at():
    """G16: branch_company_cities 必须有 created_at 字段。"""
    from app.models.d10_branch import BranchCompanyCity
    cols = {c.name for c in BranchCompanyCity.__table__.columns}
    assert "created_at" in cols, "G16 修复未应用: branch_company_cities 缺少 created_at"


def test_branch_settlement_has_updated_at():
    """G18: branch_settlements 必须有 updated_at 字段。"""
    from app.models.d10_branch import BranchSettlement
    cols = {c.name for c in BranchSettlement.__table__.columns}
    assert "updated_at" in cols, "G18 修复未应用: branch_settlements 缺少 updated_at"


def test_branch_company_city_partial_unique_index():
    from app.models.d10_branch import BranchCompanyCity
    indexes = BranchCompanyCity.__table__.indexes
    partial = [
        i for i in indexes
        if i.unique and "effective_to" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))
    ]
    assert len(partial) == 1, "branch_company_cities 缺少 UNIQUE WHERE effective_to IS NULL 部分索引"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_d8_usage_tables -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 创建 `backend/app/models/d8_usage.py`**

```python
"""
域8: 用量与报告 (2 张表)
  daily_usage · learning_report_snapshots
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

report_type_enum = sa.Enum("weekly", "monthly", name="report_type")


class DailyUsage(Base):
    """按 (user_id, usage_type, period) 记录每日用量（UPSERT 目标）。"""

    __tablename__ = "daily_usage"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    usage_type = mapped_column(sa.String, nullable=False)
    period = mapped_column(sa.Date, nullable=False)
    count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "usage_type", "period",
            name="uix_daily_usage_identity",
        ),
    )


class LearningReportSnapshot(Base):
    """学情报告快照（每生每周期唯一）。"""

    __tablename__ = "learning_report_snapshots"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    report_type = mapped_column(report_type_enum, nullable=False)
    period_start = mapped_column(sa.Date, nullable=False)
    period_end = mapped_column(sa.Date, nullable=False)
    report_data = mapped_column(JSONB, nullable=False)
    generated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "report_type", "period_start",
            name="uix_learning_report_identity",
        ),
    )
```

- [ ] **Step 4: 创建 `backend/app/models/d9_system.py`**

```python
"""
域9: 系统配置与通知 (2 张表)
  system_configs · notifications
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

notification_type_enum = sa.Enum(
    "system",
    "membership",
    "assignment",
    "analysis_done",
    "report_ready",
    "bind_request",
    "bind_accepted",
    "bind_rejected",
    "ocr_failed",
    name="notification_type",
)


class SystemConfig(Base):
    """系统参数键值对（JSONB 值，支持任意结构）。"""

    __tablename__ = "system_configs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = mapped_column(sa.String, nullable=False, unique=True)
    value = mapped_column(JSONB, nullable=False)
    description = mapped_column(sa.Text, nullable=True)
    updated_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Notification(Base):
    """站内通知（G15: 补充 read_at）。"""

    __tablename__ = "notifications"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    type = mapped_column(notification_type_enum, nullable=False)
    title = mapped_column(sa.String, nullable=False)
    content = mapped_column(sa.Text, nullable=False)
    is_read = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    # G15: is_read=true 时同步写入 read_at，便于统计消息响应时长
    read_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

- [ ] **Step 5: 创建 `backend/app/models/d10_branch.py`**

```python
"""
域10: 分公司扩展 (3 张表)
  branch_companies · branch_company_cities · branch_settlements
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base

settlement_status_enum = sa.Enum(
    "draft", "confirmed", "paid",
    name="settlement_status",
)


class BranchCompany(Base):
    """分公司主档。bank_account 在应用层 AES-256-GCM 加密后存储。"""

    __tablename__ = "branch_companies"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String, nullable=False)
    contact_phone = mapped_column(sa.String, nullable=True)
    manager_user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    commission_rate = mapped_column(sa.Numeric(5, 4), nullable=True)
    legal_name = mapped_column(sa.String, nullable=True)
    tax_number = mapped_column(sa.String, nullable=True)
    bank_name = mapped_column(sa.String, nullable=True)
    # AES-256-GCM 密文存储，解密在 service 层
    bank_account = mapped_column(sa.String, nullable=True)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class BranchCompanyCity(Base):
    """分公司负责城市（同一时刻每个城市只能归属一家分公司）。"""

    __tablename__ = "branch_company_cities"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False
    )
    city_code = mapped_column(sa.String, nullable=False)
    effective_from = mapped_column(sa.Date, nullable=False)
    effective_to = mapped_column(sa.Date, nullable=True)
    # G16: 补充 created_at
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        # 同一城市同一时刻只能有一条 effective_to IS NULL 的记录
        sa.Index(
            "uix_branch_company_cities_active_city",
            "city_code",
            unique=True,
            postgresql_where=sa.text("effective_to IS NULL"),
        ),
    )


class BranchSettlement(Base):
    """分公司对账结算单（G18: 补充 updated_at）。"""

    __tablename__ = "branch_settlements"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False
    )
    period_start = mapped_column(sa.Date, nullable=False)
    period_end = mapped_column(sa.Date, nullable=False)
    gross_revenue_fen = mapped_column(sa.Integer, nullable=False)
    refund_deduction_fen = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    net_revenue_fen = mapped_column(sa.Integer, nullable=False)
    platform_share_fen = mapped_column(sa.Integer, nullable=False)
    branch_payable_fen = mapped_column(sa.Integer, nullable=False)
    commission_rate_snapshot = mapped_column(sa.Numeric(5, 4), nullable=False)
    status = mapped_column(settlement_status_enum, nullable=False)
    confirmed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    paid_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    note = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # G18: 补充 updated_at（状态变更时更新）
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "branch_company_id", "period_start", "period_end",
            name="uix_branch_settlements_period",
        ),
    )
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `33 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/d8_usage.py backend/app/models/d9_system.py backend/app/models/d10_branch.py tests/models/test_model_structure.py
git commit -m "feat(models): add domain8-10 usage/system/branch models (7 tables, G15/G16/G18 applied)"
```

---

### Task 11: models/__init__.py — 统一导入所有模型

**Files:**
- Modify: `backend/app/models/__init__.py`
- Test: `tests/models/test_model_structure.py`

> 所有模型必须在 Alembic `env.py` 生成迁移前被导入，否则 `Base.metadata` 中没有表信息。

- [ ] **Step 1: 写失败测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_all_37_tables_in_metadata():
    """确保 Base.metadata 包含全部 37 张表。"""
    # 导入 __init__ 触发所有模型注册
    import app.models  # noqa: F401
    from app.models.base import Base

    expected_tables = {
        # 域1
        "users", "institutions", "students", "teachers",
        "relatives", "student_relatives", "teacher_students", "invite_codes",
        # 域2
        "memberships", "orders", "refund_records",
        # 域3
        "wrong_questions", "ocr_tasks", "ai_analyses",
        # 域4
        "knowledge_points", "curriculum_units", "unit_knowledge_points",
        "curriculum_words", "wrong_question_knowledge_points",
        # 域5
        "vocabulary_words", "vocabulary_learning", "essays",
        "listening_records", "study_checkins",
        # 域6
        "ai_questions", "practice_records",
        # 域7
        "classes", "class_students", "assignments", "assignment_submissions",
        # 域8
        "daily_usage", "learning_report_snapshots",
        # 域9
        "system_configs", "notifications",
        # 域10
        "branch_companies", "branch_company_cities", "branch_settlements",
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - actual_tables
    assert not missing, f"Base.metadata 缺少以下表: {sorted(missing)}"
    assert len(actual_tables) == 37, f"期望 37 张表，实际 {len(actual_tables)} 张: {sorted(actual_tables)}"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_all_37_tables_in_metadata -v
```

Expected: `AssertionError: Base.metadata 缺少以下表: [...]`（因为 `__init__.py` 是空文件）

- [ ] **Step 3: 填充 `backend/app/models/__init__.py`**

```python
"""
统一导入所有 SQLAlchemy 模型，确保 Base.metadata 中注册全部 37 张表。
Alembic env.py 中 `import app.models` 即可获取完整元数据。
"""

from .base import Base  # noqa: F401

# 域1: 用户与租户 (8 张表)
from .d1_users import (  # noqa: F401
    User,
    Institution,
    Student,
    Teacher,
    Relative,
    StudentRelative,
    TeacherStudent,
    InviteCode,
)

# 域2: 会员与支付 (3 张表)
from .d2_payments import Order, Membership, RefundRecord  # noqa: F401

# 域3: 错题与 AI 诊断 (3 张表)
from .d3_wrong_questions import WrongQuestion, OcrTask, AiAnalysis  # noqa: F401

# 域4: 知识体系 (5 张表)
from .d4_knowledge import (  # noqa: F401
    KnowledgePoint,
    CurriculumUnit,
    UnitKnowledgePoint,
    CurriculumWord,
    WrongQuestionKnowledgePoint,
)

# 域5: 学习功能 (5 张表)
from .d5_learning import (  # noqa: F401
    VocabularyWord,
    VocabularyLearning,
    Essay,
    ListeningRecord,
    StudyCheckin,
)

# 域6: AI 题库与练习 (2 张表)
from .d6_ai_questions import AiQuestion, PracticeRecord  # noqa: F401

# 域7: 老师端 (4 张表)
from .d7_teacher import (  # noqa: F401
    Class,
    ClassStudent,
    Assignment,
    AssignmentSubmission,
)

# 域8: 用量与报告 (2 张表)
from .d8_usage import DailyUsage, LearningReportSnapshot  # noqa: F401

# 域9: 系统配置与通知 (2 张表)
from .d9_system import SystemConfig, Notification  # noqa: F401

# 域10: 分公司扩展 (3 张表)
from .d10_branch import BranchCompany, BranchCompanyCity, BranchSettlement  # noqa: F401

__all__ = ["Base"]
```

- [ ] **Step 4: 运行全部测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `34 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/__init__.py tests/models/test_model_structure.py
git commit -m "feat(models): wire all 37 table models in __init__.py"
```

---

### Task 12: Alembic 配置

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`

- [ ] **Step 1: 初始化 Alembic（在 backend/ 目录内执行）**

```bash
cd backend
alembic init alembic
```

Expected:
```
Creating directory /path/to/backend/alembic ...  done
Creating directory /path/to/backend/alembic/versions ...  done
Generating /path/to/backend/alembic.ini ...  done
Generating /path/to/backend/alembic/env.py ...  done
Generating /path/to/backend/alembic/script.py.mako ...  done
```

- [ ] **Step 2: 修改 `backend/alembic.ini`，设置占位符连接（实际由 env.py 覆盖）**

找到 `sqlalchemy.url = driver://user:pass@localhost/dbname`，替换为：
```ini
sqlalchemy.url = postgresql+psycopg://placeholder/placeholder
```

> 实际 URL 由 env.py 从 `DATABASE_URL` 环境变量读取，`alembic.ini` 中的值不会被使用。

- [ ] **Step 3: 完整替换 `backend/alembic/env.py`**

```python
"""
Alembic 迁移运行环境。

关键点：
  1. 从 DATABASE_URL 环境变量读取连接（覆盖 alembic.ini 中的占位符）。
  2. import app.models 触发所有 37 张表注册到 Base.metadata。
  3. target_metadata = Base.metadata 让 autogenerate 感知模型变化。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── 加载日志配置 ─────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 导入所有模型（必须在 target_metadata 之前）────────────────────────────────
import app.models  # noqa: F401, E402
from app.models.base import Base  # noqa: E402

target_metadata = Base.metadata

# ── 从环境变量覆盖数据库连接 URL ──────────────────────────────────────────────
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


# ── offline 模式（生成 SQL 脚本，不实际连接）─────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── online 模式（直接连接数据库执行）─────────────────────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 验证 env.py 可以被 Python 导入（不需要真实数据库）**

```bash
cd backend
python -c "import alembic.config; print('alembic config ok')"
```

Expected: `alembic config ok`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako
git commit -m "feat(alembic): configure env.py with all 37 table models"
```

---

### Task 13: 生成并验证初始迁移

> **前提：** 需要一个可连接的 PostgreSQL 实例（本地或 Docker）。  
> 建议使用 Docker 快速启动：  
> `docker run -d --name enggramer-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=enggramer -p 5432:5432 postgres:16`

**Files:**
- Create: `backend/alembic/versions/0001_initial_schema.py` (autogenerate 生成后重命名)

- [ ] **Step 1: 写迁移验证测试**

在 `tests/models/test_model_structure.py` 追加：
```python
def test_migration_file_exists():
    """初始迁移文件必须存在（文件名含 initial_schema）。"""
    import os
    versions_dir = os.path.join(
        os.path.dirname(__file__), "../../backend/alembic/versions"
    )
    files = os.listdir(versions_dir)
    migration_files = [f for f in files if "initial_schema" in f and f.endswith(".py")]
    assert len(migration_files) == 1, (
        f"期望 1 个 initial_schema 迁移文件，实际找到: {migration_files}\n"
        "请先执行 Task 13 Step 2 生成迁移文件。"
    )
```

- [ ] **Step 2: 运行测试，确认失败（迁移文件还不存在）**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py::test_migration_file_exists -v
```

Expected: `AssertionError: 期望 1 个 initial_schema 迁移文件...`

- [ ] **Step 3: 确认 PostgreSQL 可连接**

```bash
export DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer"
python -c "
from sqlalchemy import create_engine, text
e = create_engine('$DATABASE_URL')
with e.connect() as c:
    print(c.execute(text('SELECT version()')).scalar())
"
```

Expected: `PostgreSQL 16.x ...`（版本号具体数字不重要）

- [ ] **Step 4: 使用 autogenerate 生成初始迁移**

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer"
alembic revision --autogenerate -m "initial_schema"
```

Expected:
```
Generating .../alembic/versions/xxxxxxxxxxxx_initial_schema.py ...  done
```

- [ ] **Step 5: 重命名迁移文件为 `0001_initial_schema.py`（便于排序）**

```bash
cd backend/alembic/versions
OLD=$(ls *initial_schema.py)
mv "$OLD" "0001_initial_schema.py"
# 同步更新文件内的 revision ID（保持不变，只改文件名）
```

- [ ] **Step 6: 检查生成的迁移文件，确认包含所有 37 张表**

```bash
cd backend
grep -c "op.create_table" alembic/versions/0001_initial_schema.py
```

Expected: 输出 `37`（每张表一个 `op.create_table` 调用）

如果数量不对，检查 `app/models/__init__.py` 是否导入了所有模型。

- [ ] **Step 7: 执行迁移，建表**

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer"
alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001..., initial_schema
```
无 ERROR。

- [ ] **Step 8: 验证数据库中有 37 张表**

```bash
psql postgresql://postgres:dev@localhost:5432/enggramer -c "
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
"
```

Expected:
```
 count
-------
    37
```

- [ ] **Step 9: 验证 alembic current 无 pending migration**

```bash
cd backend
alembic current
```

Expected:
```
0001... (head)
```

- [ ] **Step 10: 运行全部测试，确认通过**

```bash
cd backend && python -m pytest ../tests/models/test_model_structure.py -v
```

Expected: `35 passed`

- [ ] **Step 11: Commit**

```bash
git add backend/alembic/versions/0001_initial_schema.py tests/models/test_model_structure.py
git commit -m "feat(alembic): generate initial migration for all 37 tables (v3.1)"
```

---

### Task 14: 归档 D-059 并最终推送

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 在 `docs/决策归档.md` 顶部追加 D-059**

```markdown
## D-059｜Alembic 建表脚本：Python 项目脚手架 + 37 张表 SQLAlchemy 模型

**日期：** 2026-05-25
**背景：** 项目此前为纯文档状态，需从零搭建 FastAPI 后端并为 v3.1 定版的 37 张表生成 Alembic 初始建表迁移。
**结论：** 在 backend/ 目录建立 Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic 工程；按 10 个域拆分模型文件（d1_users.py … d10_branch.py）；G14-G22 所有修复直接内化进对应模型；通过 alembic revision --autogenerate 生成 0001_initial_schema.py，alembic upgrade head 验证 37 张表全部建成。RLS 策略与种子数据留给后续 migration（0002+）。
**影响范围：** backend/ 目录全新建立；docs/superpowers/plans/ 存放本计划；后续 FastAPI 路由、Service 层可直接 import 各域模型。
```

- [ ] **Step 2: Commit 并推送**

```bash
git add docs/决策归档.md
git commit -m "docs: archive D-059 Alembic initial migration decision"
git push
```

---

## 自检：Spec 覆盖与占位符扫描

**Spec 覆盖：**
| 域 | 表数 | 对应 Task |
|---|---|---|
| 域1 用户与租户 | 8 | Task 3 |
| 域2 会员与支付 | 3 | Task 4 |
| 域3 错题与AI | 3 | Task 5 |
| 域4 知识体系 | 5 | Task 6 |
| 域5 学习功能 | 5 | Task 7 |
| 域6 AI题库 | 2 | Task 8 |
| 域7 老师端 | 4 | Task 9 |
| 域8-10 用量/系统/分公司 | 7 | Task 10 |
| **合计** | **37** | ✅ |

**G14-G22 覆盖：**
| Gap | 修复位置 |
|---|---|
| G14 vocabulary_learning.created_at | Task 7 d5_learning.py |
| G15 notifications.read_at | Task 10 d9_system.py |
| G16 branch_company_cities.created_at | Task 10 d10_branch.py |
| G17 teacher_students.status += inactive | Task 3 d1_users.py |
| G18 branch_settlements.updated_at | Task 10 d10_branch.py |
| G19 memberships.order_id | Task 4 d2_payments.py |
| G20 ai_questions.updated_at | Task 8 d6_ai_questions.py |
| G21 assignments.published_at | Task 9 d7_teacher.py |
| G22 refund_records.reviewed_by | Task 4 d2_payments.py |

**占位符扫描：** 无 TBD / TODO / "similar to Task N"。每个代码步骤均包含完整可执行代码。

**类型一致性：** `UUID(as_uuid=True)` 全局统一；`sa.TIMESTAMP(timezone=True)` 代表 TIMESTAMPTZ；所有跨文件 FK 均使用字符串表名引用，SQLAlchemy 延迟解析无冲突。
