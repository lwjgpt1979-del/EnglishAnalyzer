# 机构后台基础壳 + 数据概览（D-120）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为机构管理员（role=institution_admin）提供 admin web 后台入口：同一登录页登录，按角色分流菜单，查看机构数据概览（老师/学生/会员/近7日活跃）与机构资料（可编辑名称/电话/地址）。

**Architecture:** 复用 `frontend/admin`（Vue3 + Element Plus）。后端加迁移 0019 给 `users` 表增 `institution_id` 列作机构管理员↔机构绑定键；新增 `institution_service` + `/institution/*` 路由（`require_role("institution_admin")` 鉴权 + `current_user.institution_id` 强隔离）；`admin_auth_service.authenticate` 放行 institution_admin。前端解码 JWT 取 role 决定菜单。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · Alembic · pytest · Vue3 · Element Plus · Pinia

---

## 关键约定（实现者必读）

- 后端 python 解释器：`/opt/anaconda3/bin/python`
- 测试从 `backend/` 目录运行，测试根在 `../tests/`，加 `-p no:randomly`。示例：
  `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_service.py -p no:randomly -v`
- **测试夹具沿用现有模式**：service 测试参考 `tests/services/test_assignment_service.py`（async `db` 会话夹具 + 建 User/Student/Teacher 行）；api 测试参考 `tests/api/test_assignment.py`（`client` httpx 夹具 + 登录拿 token + Bearer 头）。请打开这两个文件确认夹具确切名字后照抄签名。
- 统一响应：endpoint 用 `make_ok(...)`，`response_model=BaseResponse[T]`。
- 鉴权依赖：`require_role` 在 `app.core.security`；用法见 `app/api/v1/admin.py` 顶部 `AdminDep = Annotated[User, Depends(require_role("platform_admin"))]`。
- 迁移命令：`cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
- admin web 构建：`cd frontend/admin && npm run build`
- 本切片**不调用** LLM/媒体/支付，纯 DB，无花钱。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/alembic/versions/0019_users_institution_id.py` | 迁移：users 加 institution_id 列 + 索引 |
| `backend/app/models/d1_users.py` | User 类加 institution_id 列（同步迁移） |
| `backend/app/services/admin_auth_service.py` | authenticate 放行 institution_admin + create_institution_admin |
| `backend/app/services/institution_service.py` | get_profile / update_profile / get_overview |
| `backend/app/schemas/institution.py` | InstitutionProfileOut / InstitutionProfileUpdate / InstitutionOverviewOut |
| `backend/app/api/v1/institution.py` | GET/PATCH /profile、GET /overview |
| `backend/app/api/v1/router.py` | 注册 institution_router |
| `frontend/admin/src/api/institution.ts` | getOverview / getProfile / updateProfile |
| `frontend/admin/src/stores/auth.ts` | 登录后解码 JWT 存 role |
| `frontend/admin/src/views/InstitutionOverview.vue` | 4 张数据卡 |
| `frontend/admin/src/views/InstitutionProfile.vue` | 机构资料查看/编辑 |
| `frontend/admin/src/router/index.ts` | 加两条路由 + role 守卫 |
| `frontend/admin/src/layouts/MainLayout.vue`（或现菜单组件） | 按 role 渲染菜单 |

---

## Task 1: 迁移 0019 + User 模型加 institution_id

**Files:**
- Create: `backend/alembic/versions/0019_users_institution_id.py`
- Modify: `backend/app/models/d1_users.py`（User 类）

- [ ] **Step 1: User 模型加列**

在 `backend/app/models/d1_users.py` 的 `User` 类内，`role` 列之后加：

```python
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
```

- [ ] **Step 2: 写迁移文件**

`backend/alembic/versions/0019_users_institution_id.py`：

```python
"""users.institution_id：机构管理员↔机构绑定键（D-120）

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("institution_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_institution_id", "users", "institutions",
        ["institution_id"], ["id"],
    )
    op.create_index("ix_users_institution_id", "users", ["institution_id"])


def downgrade() -> None:
    op.drop_index("ix_users_institution_id", table_name="users")
    op.drop_constraint("fk_users_institution_id", "users", type_="foreignkey")
    op.drop_column("users", "institution_id")
```

注：若文件顶部未导入 postgresql 方言，改用 `from sqlalchemy.dialects import postgresql` 并把列类型写成 `postgresql.UUID(as_uuid=True)`。参考 `0017_vocab_wrong_book.py` 的 import 风格。

- [ ] **Step 3: 跑迁移**

Run: `cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
Expected: 输出 `Running upgrade 0018 -> 0019`，无报错。

- [ ] **Step 4: 验证列存在**

Run: `cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic current`
Expected: 显示 `0019 (head)`。

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0019_users_institution_id.py backend/app/models/d1_users.py
git commit -m "feat(institution): 迁移0019 users.institution_id + User 模型加列"
```

---

## Task 2: admin_auth_service 放行 institution_admin + create_institution_admin

**Files:**
- Modify: `backend/app/services/admin_auth_service.py`
- Test: `tests/services/test_institution_auth.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_auth.py`（夹具签名照抄 `tests/services/test_assignment_service.py`）：

```python
import pytest
from app.services import admin_auth_service


@pytest.mark.asyncio
async def test_create_and_authenticate_institution_admin(db):
    import uuid
    from app.models.d1_users import Institution
    inst = Institution(
        id=uuid.uuid4(), name="测试机构", contact_phone="13800000000",
        province_code="11", city_code="1101", address="某街1号",
    )
    db.add(inst)
    await db.flush()

    admin = await admin_auth_service.create_institution_admin(
        db, username="inst_admin1", password="pw123456", institution_id=inst.id,
    )
    await db.flush()
    assert admin.role == "institution_admin"
    assert admin.institution_id == inst.id

    ok = await admin_auth_service.authenticate(
        db, username="inst_admin1", password="pw123456",
    )
    assert ok is not None and ok.id == admin.id

    bad = await admin_auth_service.authenticate(
        db, username="inst_admin1", password="wrong",
    )
    assert bad is None
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_auth.py -p no:randomly -v`
Expected: FAIL（`create_institution_admin` 不存在 / authenticate 拒绝 institution_admin）。

- [ ] **Step 3: 改 authenticate + 加 create_institution_admin**

在 `admin_auth_service.py`：把 authenticate 里的角色判断从只允许 platform_admin 改为允许集合：

```python
    if str(user.role) not in ("platform_admin", "institution_admin"):
        return None
```

文件末尾加：

```python
async def create_institution_admin(
    db: AsyncSession, *, username: str, password: str, institution_id: uuid.UUID,
) -> User:
    """创建 / 重置一个 institution_admin 账号，绑定到指定机构。"""
    existing = (await db.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if existing is not None:
        existing.password_hash = hash_password(password)
        existing.role = "institution_admin"
        existing.institution_id = institution_id
        return existing
    user = User(
        id=uuid.uuid4(),
        openid=f"inst:{username}",
        username=username,
        password_hash=hash_password(password),
        role="institution_admin",
        institution_id=institution_id,
    )
    db.add(user)
    return user
```

- [ ] **Step 4: 跑测试看通过 + platform_admin 回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_auth.py ../tests/api/test_admin*.py -p no:randomly -v`
Expected: 新测试 PASS，原 admin 登录相关测试仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_auth_service.py tests/services/test_institution_auth.py
git commit -m "feat(institution): authenticate 放行 institution_admin + create_institution_admin"
```

---

## Task 3: institution_service — get_overview / get_profile / update_profile

**Files:**
- Create: `backend/app/services/institution_service.py`
- Test: `tests/services/test_institution_service.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_service.py`（夹具照抄 `tests/services/test_assignment_service.py`）：

```python
import uuid
import datetime as dt
import pytest

from app.models.d1_users import Institution, User, Student, Teacher
from app.models.d2_payments import Membership
from app.models.d5_learning import StudyCheckin
from app.services import institution_service


async def _mk_student(db, inst_id, *, member=False, active=False):
    uid = uuid.uuid4()
    db.add(User(id=uid, openid=f"o:{uid}", role="student"))
    db.add(Student(id=uid, institution_id=inst_id))
    if member:
        db.add(Membership(
            id=uuid.uuid4(), user_id=uid, tier="pro",
            started_at=dt.datetime.now(dt.timezone.utc), is_active=True,
        ))
    if active:
        db.add(StudyCheckin(
            id=uuid.uuid4(), student_id=uid,
            checkin_date=dt.date.today(),
            new_words_count=5, review_done=True, streak_days=1,
        ))
    return uid


@pytest.mark.asyncio
async def test_get_overview_counts(db):
    inst = Institution(
        id=uuid.uuid4(), name="A机构", contact_phone="13800000000",
        province_code="11", city_code="1101", address="A街",
    )
    db.add(inst)
    await db.flush()
    # 2 老师
    for _ in range(2):
        tid = uuid.uuid4()
        db.add(User(id=tid, openid=f"o:{tid}", role="teacher"))
        db.add(Teacher(id=tid, institution_id=inst.id))
    # 3 学生：1 付费会员、2 近7日活跃（其中含会员那位）
    await _mk_student(db, inst.id, member=True, active=True)
    await _mk_student(db, inst.id, active=True)
    await _mk_student(db, inst.id)
    await db.flush()

    ov = await institution_service.get_overview(db, institution_id=inst.id)
    assert ov["teacher_count"] == 2
    assert ov["student_count"] == 3
    assert ov["member_count"] == 1
    assert ov["active_7d_count"] == 2


@pytest.mark.asyncio
async def test_overview_isolated_between_institutions(db):
    a = Institution(id=uuid.uuid4(), name="A", contact_phone="1", province_code="11", city_code="1101", address="a")
    b = Institution(id=uuid.uuid4(), name="B", contact_phone="2", province_code="11", city_code="1101", address="b")
    db.add_all([a, b])
    await db.flush()
    await _mk_student(db, a.id)
    await _mk_student(db, b.id)
    await _mk_student(db, b.id)
    await db.flush()

    ov_a = await institution_service.get_overview(db, institution_id=a.id)
    assert ov_a["student_count"] == 1  # 不含 B 的 2 个


@pytest.mark.asyncio
async def test_update_profile(db):
    inst = Institution(id=uuid.uuid4(), name="旧名", contact_phone="111", province_code="11", city_code="1101", address="旧址")
    db.add(inst)
    await db.flush()
    updated = await institution_service.update_profile(
        db, institution_id=inst.id, name="新名", contact_phone="222", address="新址",
    )
    assert updated.name == "新名"
    assert updated.contact_phone == "222"
    assert updated.address == "新址"
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_service.py -p no:randomly -v`
Expected: FAIL（模块 / 函数不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/institution_service.py`：

```python
"""机构后台 service（D-120）：资料 + 数据概览。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Institution, Student, Teacher
from app.models.d2_payments import Membership
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d5_learning import StudyCheckin


async def get_profile(db: AsyncSession, *, institution_id: uuid.UUID) -> Institution:
    inst = (await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )).scalar_one_or_none()
    if inst is None:
        from app.core.exceptions import AppError
        raise AppError(code=404, message="机构不存在")
    return inst


async def update_profile(
    db: AsyncSession, *, institution_id: uuid.UUID,
    name: str | None = None, contact_phone: str | None = None,
    address: str | None = None,
) -> Institution:
    inst = await get_profile(db, institution_id=institution_id)
    if name is not None:
        inst.name = name
    if contact_phone is not None:
        inst.contact_phone = contact_phone
    if address is not None:
        inst.address = address
    return inst


async def get_overview(db: AsyncSession, *, institution_id: uuid.UUID) -> dict:
    teacher_count = (await db.execute(
        select(func.count()).select_from(Teacher)
        .where(Teacher.institution_id == institution_id)
    )).scalar_one()

    student_count = (await db.execute(
        select(func.count()).select_from(Student)
        .where(Student.institution_id == institution_id)
    )).scalar_one()

    # 名下学生 id 子查询
    student_ids = select(Student.id).where(Student.institution_id == institution_id)

    member_count = (await db.execute(
        select(func.count(func.distinct(Membership.user_id)))
        .where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
            Membership.tier != "free",
        )
    )).scalar_one()

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    since_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).date()
    active_checkin = select(StudyCheckin.student_id).where(
        StudyCheckin.student_id.in_(student_ids),
        StudyCheckin.checkin_date >= since_date,
    )
    active_wq = select(WrongQuestion.student_id).where(
        WrongQuestion.student_id.in_(student_ids),
        WrongQuestion.created_at >= since,
    )
    active_ids = active_checkin.union(active_wq).subquery()
    active_7d_count = (await db.execute(
        select(func.count(func.distinct(active_ids.c.student_id)))
    )).scalar_one()

    return {
        "teacher_count": teacher_count,
        "student_count": student_count,
        "member_count": member_count,
        "active_7d_count": active_7d_count,
    }
```

注：`WrongQuestion.student_id` 列名以 `backend/app/models/d3_wrong_questions.py` 实际为准（已确认为 `student_id`）。union 子查询的列名取第一个 select 的列名 `student_id`。若 `.c.student_id` 取不到，改用 `select(active_ids.c[0])`。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_service.py -p no:randomly -v`
Expected: 3 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_service.py tests/services/test_institution_service.py
git commit -m "feat(institution): institution_service 概览/资料 + 跨机构隔离测试"
```

---

## Task 4: schemas + API 路由 + 注册

**Files:**
- Create: `backend/app/schemas/institution.py`
- Create: `backend/app/api/v1/institution.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `tests/api/test_institution.py`

- [ ] **Step 1: 写 schemas**

`backend/app/schemas/institution.py`：

```python
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class InstitutionProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str
    status: str
    created_at: dt.datetime


class InstitutionProfileUpdate(BaseModel):
    name: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class InstitutionOverviewOut(BaseModel):
    teacher_count: int
    student_count: int
    member_count: int
    active_7d_count: int
```

- [ ] **Step 2: 写失败的 api 测试**

`tests/api/test_institution.py`（`client` 夹具 + 登录拿 token 的写法照抄 `tests/api/test_assignment.py`）：

```python
import uuid
import pytest

from app.models.d1_users import Institution
from app.services import admin_auth_service


async def _setup_inst_admin(db, username="instadmin", inst_name="机构A"):
    inst = Institution(
        id=uuid.uuid4(), name=inst_name, contact_phone="13800000000",
        province_code="11", city_code="1101", address="某街1号",
    )
    db.add(inst)
    await db.flush()
    await admin_auth_service.create_institution_admin(
        db, username=username, password="pw123456", institution_id=inst.id,
    )
    await db.commit()
    return inst


async def _login(client, username="instadmin", password="pw123456"):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_overview_and_profile(client, db):
    inst = await _setup_inst_admin(db)
    token = await _login(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/institution/overview", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert set(body) == {"teacher_count", "student_count", "member_count", "active_7d_count"}

    r = await client.get("/api/v1/institution/profile", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == inst.name

    r = await client.patch("/api/v1/institution/profile",
                           headers=h, json={"name": "新机构名"})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "新机构名"


@pytest.mark.asyncio
async def test_platform_admin_forbidden(client, db):
    # platform_admin 不能访问 /institution/*
    await admin_auth_service.create_admin(db, username="padmin", password="pw123456")
    await db.commit()
    token = await _login(client, username="padmin")
    h = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/v1/institution/overview", headers=h)
    assert r.status_code == 403
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution.py -p no:randomly -v`
Expected: FAIL（路由不存在 → 404）。

- [ ] **Step 4: 写 API 路由**

`backend/app/api/v1/institution.py`：

```python
"""机构管理员后台 API（D-120）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.institution import (
    InstitutionOverviewOut,
    InstitutionProfileOut,
    InstitutionProfileUpdate,
)
from app.services import institution_service

router = APIRouter(prefix="/institution", tags=["institution"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
InstAdminDep = Annotated[User, Depends(require_role("institution_admin"))]


def _require_inst(admin: User):
    if admin.institution_id is None:
        raise AppError(code=400, message="该管理员未绑定机构")
    return admin.institution_id


@router.get("/overview", response_model=BaseResponse[InstitutionOverviewOut])
async def get_overview(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    data = await institution_service.get_overview(db, institution_id=inst_id)
    return make_ok(InstitutionOverviewOut(**data))


@router.get("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def get_profile(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.get_profile(db, institution_id=inst_id)
    return make_ok(InstitutionProfileOut.model_validate(inst))


@router.patch("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def update_profile(body: InstitutionProfileUpdate, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.update_profile(
        db, institution_id=inst_id,
        name=body.name, contact_phone=body.contact_phone, address=body.address,
    )
    await db.commit()
    await db.refresh(inst)
    return make_ok(InstitutionProfileOut.model_validate(inst))
```

- [ ] **Step 5: 注册路由**

在 `backend/app/api/v1/router.py`：import 处加 `from app.api.v1.institution import router as institution_router`；注册处（admin_router 之前）加 `v1_router.include_router(institution_router)`。

- [ ] **Step 6: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution.py -p no:randomly -v`
Expected: 2 PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py backend/app/api/v1/router.py tests/api/test_institution.py
git commit -m "feat(institution): /institution overview+profile API + 鉴权隔离测试"
```

---

## Task 5: 后端全量回归

**Files:** 无（仅验证）

- [ ] **Step 1: 跑全量测试**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 全绿（已知偶发污染项 `test_get_wrong_question_api`/`test_mark_mastered_api`/`test_analyze_endpoint` 若失败，单独复跑确认隔离通过）。新增 institution 测试全 PASS。

- [ ] **Step 2: 若有失败，单测隔离复跑确认非本切片回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_wrong_questions.py::test_get_wrong_question_api -p no:randomly -v`
Expected: 隔离运行 PASS（确认是已知偶发，非本切片引入）。

---

## Task 6: 前端 — auth store 解码 role + api 层

**Files:**
- Modify: `frontend/admin/src/stores/auth.ts`
- Create: `frontend/admin/src/api/institution.ts`

- [ ] **Step 1: auth store 存 role**

打开 `frontend/admin/src/stores/auth.ts`，在 login 成功拿到 token 后解码 JWT payload 取 role 并持久化。在 `login` 内 token 赋值后加：

```typescript
  // 解码 JWT payload 取 role（payload 形如 {sub, role, exp}）
  function decodeRole(t: string): string {
    try {
      const payload = JSON.parse(
        decodeURIComponent(escape(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))),
      )
      return payload.role || ''
    } catch {
      return ''
    }
  }
```

新增响应式 `const role = ref<string>(localStorage.getItem('admin_role') || '')`，login 成功后 `role.value = decodeRole(accessToken); localStorage.setItem('admin_role', role.value)`；logout 时 `role.value = ''; localStorage.removeItem('admin_role')`。把 `role` 加入 store return。

> 实现者注意：照搬现有 token 的存取写法（同一个 store 里 token 怎么存 role 就怎么存），保持一致。

- [ ] **Step 2: api 层**

`frontend/admin/src/api/institution.ts`：

```typescript
import request from './request'

export interface InstitutionOverview {
  teacher_count: number
  student_count: number
  member_count: number
  active_7d_count: number
}

export interface InstitutionProfile {
  id: string
  name: string
  contact_phone: string
  province_code: string
  city_code: string
  address: string
  status: string
  created_at: string
}

export function getOverview() {
  return request.get<unknown, InstitutionOverview>('/institution/overview')
}

export function getProfile() {
  return request.get<unknown, InstitutionProfile>('/institution/profile')
}

export function updateProfile(data: Partial<Pick<InstitutionProfile, 'name' | 'contact_phone' | 'address'>>) {
  return request.patch<unknown, InstitutionProfile>('/institution/profile', data)
}
```

> 实现者注意：`request` 的导入路径与返回拆包方式照抄现有 `frontend/admin/src/api/*.ts`（如 essay 模板那个 api 文件）；若现有 request 已自动返回 `data` 内层，则上面的泛型按现有约定调整。

- [ ] **Step 3: 类型/构建校验**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功，无 TS 报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/admin/src/stores/auth.ts frontend/admin/src/api/institution.ts
git commit -m "feat(institution-web): auth store 解码 role + institution api 层"
```

---

## Task 7: 前端 — 概览页 + 资料页 + 路由 + 菜单

**Files:**
- Create: `frontend/admin/src/views/InstitutionOverview.vue`
- Create: `frontend/admin/src/views/InstitutionProfile.vue`
- Modify: `frontend/admin/src/router/index.ts`
- Modify: `frontend/admin/src/layouts/MainLayout.vue`（实际菜单文件名以仓库为准）

- [ ] **Step 1: 概览页**

`frontend/admin/src/views/InstitutionOverview.vue`：

```vue
<template>
  <div class="overview">
    <el-row :gutter="16">
      <el-col :span="6"><el-card><div class="label">老师数</div><div class="num">{{ data.teacher_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">学生数</div><div class="num">{{ data.student_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">付费会员</div><div class="num">{{ data.member_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">近7日活跃</div><div class="num">{{ data.active_7d_count }}</div></el-card></el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { getOverview } from '@/api/institution'

const data = reactive({ teacher_count: 0, student_count: 0, member_count: 0, active_7d_count: 0 })

onMounted(async () => {
  Object.assign(data, await getOverview())
})
</script>

<style scoped>
.label { color: #888; font-size: 14px; }
.num { font-size: 32px; font-weight: 700; margin-top: 8px; }
</style>
```

- [ ] **Step 2: 资料页**

`frontend/admin/src/views/InstitutionProfile.vue`：

```vue
<template>
  <el-card style="max-width: 560px">
    <el-form label-width="100px">
      <el-form-item label="机构名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="联系电话"><el-input v-model="form.contact_phone" /></el-form-item>
      <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
      <el-form-item label="省/市编码"><span>{{ form.province_code }} / {{ form.city_code }}</span></el-form-item>
      <el-form-item label="状态"><el-tag>{{ form.status }}</el-tag></el-form-item>
      <el-form-item><el-button type="primary" @click="save">保存</el-button></el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { getProfile, updateProfile } from '@/api/institution'

const form = reactive({ name: '', contact_phone: '', address: '', province_code: '', city_code: '', status: '' })

onMounted(async () => { Object.assign(form, await getProfile()) })

async function save() {
  const r = await updateProfile({ name: form.name, contact_phone: form.contact_phone, address: form.address })
  Object.assign(form, r)
  ElMessage.success('已保存')
}
</script>
```

- [ ] **Step 3: 路由**

在 `frontend/admin/src/router/index.ts` 的受保护子路由数组内加（照抄现有子路由对象结构，含 meta）：

```typescript
{ path: 'institution/overview', name: 'InstitutionOverview', component: () => import('@/views/InstitutionOverview.vue'), meta: { title: '机构概览', roles: ['institution_admin'] } },
{ path: 'institution/profile', name: 'InstitutionProfile', component: () => import('@/views/InstitutionProfile.vue'), meta: { title: '机构资料', roles: ['institution_admin'] } },
```

在现有全局 `beforeEach` 守卫里（若已存在）加：登录后若 `to.meta.roles` 存在且不含当前 role → 重定向到该 role 默认页（institution_admin → `/institution/overview`，platform_admin → 现有首页）。若现有守卫只判登录态，则追加：

```typescript
  const role = useAuthStore().role
  if (to.meta.roles && Array.isArray(to.meta.roles) && !to.meta.roles.includes(role)) {
    return next(role === 'institution_admin' ? '/institution/overview' : '/')
  }
```

> 实现者注意：`useAuthStore` 导入与现有守卫保持一致；若守卫文件不在 router/index.ts 而在单独文件，改对应文件。

- [ ] **Step 4: 菜单按 role 渲染**

在菜单组件（`MainLayout.vue` 或现有侧边栏组件）里，用 `authStore.role` 条件渲染：institution_admin 只显示「机构概览 / 机构资料」两项；platform_admin 显示现有全部菜单。照抄现有 `<el-menu-item>` 结构，外层包 `v-if="authStore.role === 'institution_admin'"` / `v-else`。

- [ ] **Step 5: 构建校验**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功，无 TS 报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/admin/src/views/InstitutionOverview.vue frontend/admin/src/views/InstitutionProfile.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(institution-web): 概览页+资料页+路由role守卫+菜单分流"
```

---

## Task 8: 同步模型导入检查 + 归档 D-120

**Files:**
- Modify: `docs/决策归档.md`（顶部追加 D-120）
- Modify: `docs/上线前清单.md`（E 节加机构端验证行）

- [ ] **Step 1: 确认 User.institution_id 不破坏 models 导入**

Run: `cd backend && /opt/anaconda3/bin/python -c "from app.models.d1_users import User; print('institution_id' in User.__table__.columns)"`
Expected: `True`。

- [ ] **Step 2: 归档 D-120**

在 `docs/决策归档.md` 顶部按既有格式追加 D-120 条目（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-119、需求 5.1 5B）。

- [ ] **Step 3: 上线前清单补一行**

在 `docs/上线前清单.md` E 节加机构端验证行（机构管理员登录→概览→资料编辑）。

- [ ] **Step 4: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md
git commit -m "docs: 归档 D-120 机构后台基础壳+数据概览"
```

---

## Self-Review 结论

- **Spec 覆盖**：迁移 0019→Task1；authenticate 放行+create→Task2；overview/profile/隔离→Task3；schemas/API/注册/403→Task4；回归→Task5；前端 role 解码+api→Task6；两页+路由守卫+菜单→Task7；归档→Task8。全覆盖。
- **占位符**：无 TBD/TODO；每个改代码步骤均含完整代码；前端少数“照抄现有写法”处已点名具体参照文件（request 拆包、菜单结构、守卫）——因这些依赖仓库既有约定，给出明确参照而非空泛描述。
- **类型一致**：`get_overview` 返回 dict 四键 ↔ `InstitutionOverviewOut` 四字段 ↔ 测试断言四键，一致；`create_institution_admin(username,password,institution_id)` 签名在 Task2 定义、Task4 测试调用一致；`update_profile(name,contact_phone,address)` 三处一致。
