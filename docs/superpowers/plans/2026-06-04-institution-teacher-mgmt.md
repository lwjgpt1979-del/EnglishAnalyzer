# 机构端切片二：名下老师账号管理（D-121）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构管理员在 admin web 生成机构加入邀请码、查看名下老师、移出老师；老师在小程序输 6 位码加入机构。

**Architecture:** 复用 `InviteCode`（`institution_join`）+ `relative_service` 的 6 位码生成范式。机构归属在邀请码消费时由 `issuer(User).institution_id` 决定；移出 = `teachers.institution_id=None`。零迁移、无付费调用。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest · Vue3 · Element Plus · uni-app

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，加 `-p no:randomly`。
- **测试夹具**：service 测试用本地 `db_session` 夹具（`async with _async_session_factory() as s: yield s; await s.rollback()`），见 `tests/services/test_institution_service.py`；api 测试用本地 `client` 夹具 + `/api/v1/admin/auth/login` 拿 token，见 `tests/api/test_institution.py`；老师登录走 `/api/v1/auth/wx-login`（patch `wechat_code2session`），见 `tests/api/test_assignment.py` 的 `_login`。
- 统一响应 `make_ok` + `BaseResponse[T]`；鉴权 `require_role`（见 `app/api/v1/institution.py` 的 `InstAdminDep`）。
- 邀请码生成范式见 `relative_service.generate_invite_code`（`_unique_code` 10 次重试查重）。
- admin web 构建：`cd frontend/admin && npm run build`；小程序构建：`cd frontend/miniprogram && npm run build:mp-weixin`。
- 本切片**不调用** LLM/媒体/支付，纯 DB，无花钱，无迁移。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/institution_service.py` | +generate_join_code / list_teachers / remove_teacher |
| `backend/app/services/teacher_service.py` | +join_institution |
| `backend/app/schemas/institution.py` | +InviteCodeOut / InstitutionTeacherOut / JoinInstitutionRequest |
| `backend/app/api/v1/institution.py` | +邀请码/列表/移除 endpoints |
| `backend/app/api/v1/teacher.py` | +join-institution endpoint |
| `frontend/admin/src/api/institution.ts` | +老师管理 3 接口 |
| `frontend/admin/src/views/InstitutionTeachers.vue` | 老师管理页 |
| `frontend/admin/src/router/index.ts` | +老师管理路由 |
| `frontend/admin/src/layouts/MainLayout.vue` | +老师管理菜单 |
| `frontend/miniprogram/src/api/teacher.ts` | +joinInstitution |
| `frontend/miniprogram/src/pages/teacher/join-institution.vue` | 老师输码加入页 |
| `frontend/miniprogram/src/pages.json` | 注册新页 |

---

## Task 1: institution_service — 生成码 / 列表 / 移除

**Files:**
- Modify: `backend/app/services/institution_service.py`
- Test: `tests/services/test_institution_teacher.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_teacher.py`：

```python
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Teacher, User
from app.services import institution_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="138",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    return inst


async def _teacher(s, inst_id, *, nickname="王老师"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="teacher", nickname=nickname))
    await s.flush()
    s.add(Teacher(id=uid, institution_id=inst_id))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_generate_join_code(db_session):
    inst = await _inst(db_session)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin",
                        institution_id=inst.id))
    await db_session.flush()
    code = await institution_service.generate_join_code(
        db_session, institution_id=inst.id, issuer_id=admin)
    assert len(code.code) == 6
    assert str(code.type) == "institution_join"


@pytest.mark.asyncio
async def test_list_teachers_isolated(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    await _teacher(db_session, a.id)
    await _teacher(db_session, b.id)
    rows = await institution_service.list_teachers(db_session, institution_id=a.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_remove_teacher(db_session):
    a = await _inst(db_session, "A")
    tid = await _teacher(db_session, a.id)
    await institution_service.remove_teacher(db_session, institution_id=a.id, teacher_id=tid)
    t = await db_session.get(Teacher, tid)
    assert t.institution_id is None


@pytest.mark.asyncio
async def test_remove_teacher_cross_institution_404(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    tid = await _teacher(db_session, b.id)
    with pytest.raises(AppError):
        await institution_service.remove_teacher(db_session, institution_id=a.id, teacher_id=tid)
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_teacher.py -p no:randomly -q`
Expected: FAIL（函数不存在）。

- [ ] **Step 3: 实现 service 函数**

在 `backend/app/services/institution_service.py` 顶部 import 补：

```python
import random
import string
from datetime import timedelta
from app.models.d1_users import InviteCode, Teacher, User
```

（`datetime`/`uuid`/`select` 已在文件内；若 `dt` 已 import 为 `import datetime as dt`，下面用 `dt.datetime`/`dt.timedelta`，与文件现有风格一致。）

文件末尾加：

```python
_CODE_CHARS = string.ascii_uppercase + string.digits
_JOIN_CODE_TTL_HOURS = 24 * 7


async def generate_join_code(
    db: AsyncSession, *, institution_id: uuid.UUID, issuer_id: uuid.UUID
) -> InviteCode:
    async def _unique() -> str:
        for _ in range(10):
            code = "".join(random.choices(_CODE_CHARS, k=6))
            r = await db.execute(select(InviteCode).where(InviteCode.code == code))
            if r.scalar_one_or_none() is None:
                return code
        raise AppError(code=500, message="邀请码生成失败，请重试")

    invite = InviteCode(
        id=uuid.uuid4(),
        code=await _unique(),
        type="institution_join",  # type: ignore[arg-type]
        issuer_id=issuer_id,
        target_id=None,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=_JOIN_CODE_TTL_HOURS),
    )
    db.add(invite)
    await db.flush()
    return invite


async def list_teachers(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> list[tuple[Teacher, User]]:
    rows = (await db.execute(
        select(Teacher, User)
        .join(User, User.id == Teacher.id)
        .where(Teacher.institution_id == institution_id)
    )).all()
    return [(t, u) for t, u in rows]


async def remove_teacher(
    db: AsyncSession, *, institution_id: uuid.UUID, teacher_id: uuid.UUID
) -> None:
    t = (await db.execute(
        select(Teacher).where(
            Teacher.id == teacher_id, Teacher.institution_id == institution_id
        )
    )).scalar_one_or_none()
    if t is None:
        raise AppError(code=404, message="老师不存在或不属于本机构")
    t.institution_id = None
    await db.flush()
```

注：若文件用的是 `from datetime import datetime, timezone, timedelta` 而非 `import datetime as dt`，把 `dt.datetime`/`dt.timezone`/`dt.timedelta` 改为 `datetime`/`timezone`/`timedelta`。以文件现有 import 为准（D-120 时该文件用 `import datetime as dt`）。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_teacher.py -p no:randomly -q`
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_service.py tests/services/test_institution_teacher.py
git commit -m "feat(institution): 生成机构邀请码/名下老师列表/移出机构 service"
```

---

## Task 2: teacher_service.join_institution

**Files:**
- Modify: `backend/app/services/teacher_service.py`
- Test: `tests/services/test_teacher_join.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_teacher_join.py`：

```python
import uuid
import datetime as dt
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, InviteCode, Teacher, User
from app.services import teacher_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _setup(s):
    inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    admin = uuid.uuid4()
    s.add(User(id=admin, openid=f"o:{admin}", role="institution_admin",
               institution_id=inst.id))
    tid = uuid.uuid4()
    s.add(User(id=tid, openid=f"o:{tid}", role="teacher"))
    await s.flush()
    s.add(Teacher(id=tid))
    code = InviteCode(id=uuid.uuid4(), code="ABC123", type="institution_join",
                      issuer_id=admin, target_id=None,
                      expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1))
    s.add(code)
    await s.flush()
    return inst, tid


@pytest.mark.asyncio
async def test_join_institution_ok(db_session):
    inst, tid = await _setup(db_session)
    t = await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ABC123")
    assert t.institution_id == inst.id
    code = (await db_session.execute(
        __import__("sqlalchemy").select(InviteCode).where(InviteCode.code == "ABC123")
    )).scalar_one()
    assert code.used_at is not None


@pytest.mark.asyncio
async def test_join_bad_code(db_session):
    _, tid = await _setup(db_session)
    with pytest.raises(AppError):
        await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ZZZZZZ")


@pytest.mark.asyncio
async def test_join_when_already_in_institution(db_session):
    inst, tid = await _setup(db_session)
    await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ABC123")
    # 再用另一码加入应 409
    admin2 = (await db_session.execute(
        __import__("sqlalchemy").select(User).where(User.role == "institution_admin")
    )).scalars().first()
    code2 = InviteCode(id=uuid.uuid4(), code="DEF456", type="institution_join",
                       issuer_id=admin2.id, target_id=None,
                       expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1))
    db_session.add(code2)
    await db_session.flush()
    with pytest.raises(AppError):
        await teacher_service.join_institution(db_session, teacher_user_id=tid, code="DEF456")
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_teacher_join.py -p no:randomly -q`
Expected: FAIL（join_institution 不存在）。

- [ ] **Step 3: 实现 join_institution**

在 `backend/app/services/teacher_service.py` 末尾加（import 区补 `from app.models.d1_users import InviteCode, Teacher, User` 中缺的；`datetime`/`select` 按文件现有风格）：

```python
async def join_institution(
    db: AsyncSession, *, teacher_user_id: uuid.UUID, code: str
) -> Teacher:
    now = datetime.now(timezone.utc)
    invite = (await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.type == "institution_join",
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
    )).scalar_one_or_none()
    if invite is None:
        raise AppError(code=400, message="邀请码无效或已过期")

    issuer = await db.get(User, invite.issuer_id)
    if issuer is None or issuer.institution_id is None:
        raise AppError(code=400, message="邀请码所属机构无效")

    teacher = await db.get(Teacher, teacher_user_id)
    if teacher is None:
        raise AppError(code=404, message="老师档案不存在")
    if teacher.institution_id is not None:
        raise AppError(code=409, message="您已加入机构，不能重复加入")

    teacher.institution_id = issuer.institution_id
    invite.used_at = now
    invite.target_id = teacher_user_id
    await db.flush()
    return teacher
```

注：`datetime`/`timezone`/`select`/`AppError`/`uuid` 以 teacher_service.py 现有 import 为准（该文件已 import 这些；只需补 `InviteCode` 到 models import 行）。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_teacher_join.py -p no:randomly -q`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/teacher_service.py tests/services/test_teacher_join.py
git commit -m "feat(teacher): 老师输码加入机构 join_institution service"
```

---

## Task 3: schemas + API（管理员 3 个 + 老师 1 个）

**Files:**
- Modify: `backend/app/schemas/institution.py`
- Modify: `backend/app/api/v1/institution.py`
- Modify: `backend/app/api/v1/teacher.py`
- Test: `tests/api/test_institution_teacher.py`

- [ ] **Step 1: 加 schemas**

在 `backend/app/schemas/institution.py` 末尾加：

```python
class InviteCodeOut(BaseModel):
    code: str
    expires_at: dt.datetime


class InstitutionTeacherOut(BaseModel):
    id: uuid.UUID
    nickname: str | None = None
    phone: str | None = None
    subject: str | None = None
    cert_status: str


class JoinInstitutionRequest(BaseModel):
    code: str
```

- [ ] **Step 2: 写失败的 api 测试**

`tests/api/test_institution_teacher.py`：

```python
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Teacher, User
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _setup_admin(username, inst_name="机构A"):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="138",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()
        return inst.id


async def _admin_login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _teacher_login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=h)).json()["data"]
    uid = uuid.UUID(me["id"])
    async with _async_session_factory() as s:
        u = await s.get(User, uid)
        u.role = "teacher"
        s.add(Teacher(id=uid))
        await s.commit()
    return h, uid


@pytest.mark.asyncio
async def test_invite_join_list_remove_flow(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    inst_id = await _setup_admin(uname)
    ah = await _admin_login(client, uname)

    code = (await client.post("/api/v1/institution/teachers/invite-code", headers=ah)).json()["data"]["code"]

    th, tid = await _teacher_login(client, f"t_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/teacher/join-institution", headers=th, json={"code": code})
    assert r.status_code == 200

    rows = (await client.get("/api/v1/institution/teachers", headers=ah)).json()["data"]
    assert any(t["id"] == str(tid) for t in rows)

    r = await client.delete(f"/api/v1/institution/teachers/{tid}", headers=ah)
    assert r.status_code == 200
    rows = (await client.get("/api/v1/institution/teachers", headers=ah)).json()["data"]
    assert not any(t["id"] == str(tid) for t in rows)


@pytest.mark.asyncio
async def test_cross_institution_remove_404(client):
    ua = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(ua, "A")
    ah = await _admin_login(client, ua)
    # B 机构 + B 老师
    ub = f"ib_{uuid.uuid4().hex[:6]}"
    b_inst = await _setup_admin(ub, "B")
    async with _async_session_factory() as s:
        btid = uuid.uuid4()
        s.add(User(id=btid, openid=f"o:{btid}", role="teacher"))
        await s.flush()
        s.add(Teacher(id=btid, institution_id=b_inst))
        await s.commit()
    r = await client.delete(f"/api/v1/institution/teachers/{btid}", headers=ah)
    assert r.status_code == 404
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_teacher.py -p no:randomly -q`
Expected: FAIL（endpoint 不存在 → 404/405）。

- [ ] **Step 4: 加管理员 endpoints**

在 `backend/app/api/v1/institution.py` import 区补：

```python
import uuid
from app.schemas.institution import (
    InstitutionOverviewOut, InstitutionProfileOut, InstitutionProfileUpdate,
    InviteCodeOut, InstitutionTeacherOut, JoinInstitutionRequest,
)
```

（把已有的 institution schema import 合并；`JoinInstitutionRequest` 在 institution.py 不用也可不导，留给 teacher.py。）

文件末尾加：

```python
@router.post("/teachers/invite-code", response_model=BaseResponse[InviteCodeOut])
async def gen_teacher_invite_code(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    invite = await institution_service.generate_join_code(
        db, institution_id=inst_id, issuer_id=admin.id)
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.get("/teachers", response_model=BaseResponse[list[InstitutionTeacherOut]])
async def list_institution_teachers(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_service.list_teachers(db, institution_id=inst_id)
    return make_ok([
        InstitutionTeacherOut(
            id=t.id, nickname=u.nickname, phone=u.phone,
            subject=t.subject, cert_status=str(t.cert_status),
        ) for t, u in rows
    ])


@router.delete("/teachers/{teacher_id}", response_model=BaseResponse[dict])
async def remove_institution_teacher(teacher_id: uuid.UUID, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    await institution_service.remove_teacher(db, institution_id=inst_id, teacher_id=teacher_id)
    await db.commit()
    return make_ok({"removed": str(teacher_id)})
```

- [ ] **Step 5: 加老师 join endpoint**

在 `backend/app/api/v1/teacher.py`：import 区补 `from app.core.security import require_role`、`from app.schemas.institution import InstitutionTeacherOut, JoinInstitutionRequest`、`from app.services import teacher_service`（按已有 import 风格）；文件末尾加：

```python
TeacherDep = Annotated[User, Depends(require_role("teacher"))]


@router.post("/join-institution", response_model=BaseResponse[InstitutionTeacherOut])
async def join_institution(
    body: JoinInstitutionRequest, db: DbDep, current_user: TeacherDep,
):
    t = await teacher_service.join_institution(
        db, teacher_user_id=current_user.id, code=body.code)
    await db.commit()
    await db.refresh(t)
    return make_ok(InstitutionTeacherOut(
        id=t.id, nickname=current_user.nickname, phone=current_user.phone,
        subject=t.subject, cert_status=str(t.cert_status),
    ))
```

注：确认 teacher.py 顶部已有 `from typing import Annotated`、`from fastapi import Depends`、`make_ok`、`BaseResponse`、`DbDep`；缺则补。`/join-institution` 为静态路径，须在任何 `/{...}` 动态路由之前注册（teacher.py 若有动态路由，把本段插到其前）。

- [ ] **Step 6: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_teacher.py -p no:randomly -q`
Expected: 2 passed。

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py backend/app/api/v1/teacher.py tests/api/test_institution_teacher.py
git commit -m "feat(institution): 老师管理 API（生成码/列表/移除 + 老师 join）"
```

---

## Task 4: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 9 测试全过；已知偶发污染项（test_create_wrong_question_api / test_add_comment_and_get_comments_api 等）若红，隔离复跑确认通过。

- [ ] **Step 2: 偶发项隔离复跑（如需）**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_wrong_questions.py::test_create_wrong_question_api ../tests/api/test_teacher.py::test_add_comment_and_get_comments_api -p no:randomly -q`
Expected: PASS（确认非本切片回归）。

---

## Task 5: admin web — 老师管理页

**Files:**
- Modify: `frontend/admin/src/api/institution.ts`
- Create: `frontend/admin/src/views/InstitutionTeachers.vue`
- Modify: `frontend/admin/src/router/index.ts`
- Modify: `frontend/admin/src/layouts/MainLayout.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/institution.ts` 末尾加：

```typescript
export interface InstitutionTeacher {
  id: string
  nickname: string | null
  phone: string | null
  subject: string | null
  cert_status: string
}

export function generateTeacherInviteCode(): Promise<{ code: string; expires_at: string }> {
  return unwrap(request.post('/institution/teachers/invite-code'))
}

export function listTeachers(): Promise<InstitutionTeacher[]> {
  return unwrap<InstitutionTeacher[]>(request.get('/institution/teachers'))
}

export function removeTeacher(teacherId: string): Promise<{ removed: string }> {
  return unwrap(request.delete(`/institution/teachers/${teacherId}`))
}
```

- [ ] **Step 2: 老师管理页**

`frontend/admin/src/views/InstitutionTeachers.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { generateTeacherInviteCode, listTeachers, removeTeacher, type InstitutionTeacher } from '../api/institution'

const teachers = ref<InstitutionTeacher[]>([])
const inviteCode = ref('')
const inviteExpire = ref('')

async function load() {
  teachers.value = await listTeachers()
}

async function genCode() {
  const r = await generateTeacherInviteCode()
  inviteCode.value = r.code
  inviteExpire.value = r.expires_at.slice(0, 16).replace('T', ' ')
}

async function remove(t: InstitutionTeacher) {
  await ElMessageBox.confirm(`确认把「${t.nickname || t.id}」移出机构？`, '提示', { type: 'warning' })
  await removeTeacher(t.id)
  ElMessage.success('已移出')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">老师管理</h2>
    <el-card style="margin-bottom: 16px">
      <el-button type="primary" @click="genCode">生成机构邀请码</el-button>
      <span v-if="inviteCode" class="code-tip">
        邀请码：<b>{{ inviteCode }}</b>（有效期至 {{ inviteExpire }}）— 让老师在小程序「加入机构」输入
      </span>
    </el-card>
    <el-table :data="teachers" border>
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="phone" label="电话" />
      <el-table-column prop="subject" label="科目" />
      <el-table-column prop="cert_status" label="认证状态" />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button type="danger" text @click="remove(row)">移出机构</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.code-tip { margin-left: 16px; color: #555; }
</style>
```

- [ ] **Step 3: 路由**

在 `frontend/admin/src/router/index.ts` 的 children 内（机构两条之后）加：

```typescript
        { path: 'institution/teachers', name: 'institution-teachers', component: () => import('../views/InstitutionTeachers.vue'), meta: { roles: ['institution_admin'] } },
```

- [ ] **Step 4: 菜单**

在 `frontend/admin/src/layouts/MainLayout.vue` 的 `institution_admin` 分支内（机构资料之后）加：

```html
          <el-menu-item index="/institution/teachers">老师管理</el-menu-item>
```

- [ ] **Step 5: 构建校验**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功，无 TS 报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/admin/src/api/institution.ts frontend/admin/src/views/InstitutionTeachers.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(institution-web): 老师管理页（生成邀请码/列表/移出）"
```

---

## Task 6: 小程序老师端 — 输码加入页

**Files:**
- Modify: `frontend/miniprogram/src/api/teacher.ts`
- Create: `frontend/miniprogram/src/pages/teacher/join-institution.vue`
- Modify: `frontend/miniprogram/src/pages.json`
- Modify: 老师端入口（`pages/teacher/index.vue` 或个人中心，加按钮）

- [ ] **Step 1: api**

在 `frontend/miniprogram/src/api/teacher.ts` 末尾加（`request` 导入与拆包照抄文件内现有函数风格）：

```typescript
export function joinInstitution(code: string) {
  return request('/api/v1/teacher/join-institution', { method: 'POST', data: { code } })
}
```

- [ ] **Step 2: 加入页**

`frontend/miniprogram/src/pages/teacher/join-institution.vue`：

```vue
<template>
  <view class="page">
    <view class="hint">输入机构管理员提供的 6 位邀请码加入机构</view>
    <input class="code-input" v-model="code" placeholder="6 位邀请码" maxlength="6" />
    <button class="btn" :disabled="code.length < 6" @tap="submit">加入机构</button>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { joinInstitution } from '@/api/teacher'

const code = ref('')

async function submit() {
  try {
    await joinInstitution(code.value.trim().toUpperCase())
    uni.showToast({ title: '加入成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
</script>

<style scoped>
.page { padding: 48rpx; }
.hint { color: var(--c-text-second); font-size: 28rpx; margin-bottom: 32rpx; }
.code-input { background: var(--c-bg-card); border-radius: var(--r-md); padding: 24rpx; font-size: 36rpx; letter-spacing: 8rpx; text-align: center; }
.btn { margin-top: 48rpx; background: var(--c-primary); color: var(--c-ink); font-weight: 700; border-radius: var(--r-btn); }
</style>
```

- [ ] **Step 3: 注册页面**

在 `frontend/miniprogram/src/pages.json` 的 `pages` 数组加：

```json
    { "path": "pages/teacher/join-institution", "style": { "navigationBarTitleText": "加入机构" } }
```

- [ ] **Step 4: 老师端入口按钮**

在老师端页面（`pages/teacher/index.vue`，若不存在则在个人中心 `pages/profile/index.vue` 的老师区块）加一个按钮：

```html
<button class="entry-btn" @tap="() => uni.navigateTo({ url: '/pages/teacher/join-institution' })">加入机构</button>
```

（样式照抄该页现有按钮 class；仅老师角色可见时，用现有 role 判断包裹。）

- [ ] **Step 5: 构建校验**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: 构建成功，无报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/miniprogram/src/api/teacher.ts frontend/miniprogram/src/pages/teacher/join-institution.vue frontend/miniprogram/src/pages.json frontend/miniprogram/src/pages/teacher/index.vue
git commit -m "feat(teacher-mp): 老师输码加入机构页 + 入口"
```

---

## Task 7: 归档 D-121 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`（顶部追加 D-121）
- Modify: `docs/上线前清单.md`（机构端验证加 M4；老师端加输码加入）

- [ ] **Step 1: 归档**

在 `docs/决策归档.md` 顶部按既有格式加 D-121（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-120）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` 机构管理员后台表加 M4（老师管理：生成码/列表/移出）；老师端表加一行（输码加入机构）。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-teacher-mgmt.md
git commit -m "docs: 归档 D-121 名下老师账号管理"
```

---

## Self-Review 结论

- **Spec 覆盖**：生成码/列表/移出→Task1；老师 join→Task2；schemas+4 endpoints→Task3；回归→Task4；admin 老师管理页→Task5；小程序输码页→Task6；归档→Task7。全覆盖。
- **占位符**：无 TBD；每个改码步骤含完整代码；前端少数“照抄现有风格”处点名了参照文件（request 拆包、按钮样式、role 判断）。
- **类型一致**：`generate_join_code(institution_id,issuer_id)`、`list_teachers→list[(Teacher,User)]`、`remove_teacher(institution_id,teacher_id)`、`join_institution(teacher_user_id,code)` 在 service/api/test 三处签名一致；`InstitutionTeacherOut` 字段（id/nickname/phone/subject/cert_status）在 service 拼装、api 返回、前端 interface、测试断言一致；邀请码字段 code/expires_at 一致。
