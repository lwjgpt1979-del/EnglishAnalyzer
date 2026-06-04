# 机构端切片四：入驻审核（超管侧，D-123）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 平台超管在 admin web 录入待审核机构、按状态查看、审核通过（机构 active + 开通机构管理员账号返回账号密码）或拒绝（机构 suspended）。

**Architecture:** 端点挂 `/admin/*`（复用 `AdminDep=require_role("platform_admin")`）。拒绝=suspended（零迁移）。通过时复用 `admin_auth_service.create_institution_admin` 开通账号，明文密码仅本次返回。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 测试夹具：service 用本地 `db_session`（`_async_session_factory`），见 `tests/services/test_institution_teacher.py`；api 用本地 `client` + `/api/v1/admin/auth/login`（platform_admin 用 `admin_auth_service.create_admin` 种子；institution_admin 用 `create_institution_admin`），见 `tests/api/test_institution_teacher.py`。
- 统一响应 `make_ok` + `BaseResponse[T]`；`AdminDep` 已在 `admin.py` 定义（platform_admin）。
- 本切片**无迁移、无付费调用**，纯 DB。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/admin_institution_service.py` | create/list/approve/reject 机构 |
| `backend/app/schemas/institution.py` | +Admin 审核相关 schemas |
| `backend/app/api/v1/admin.py` | +机构审核 4 endpoints |
| `frontend/admin/src/api/admin.ts` | +机构审核 4 接口 |
| `frontend/admin/src/views/Institutions.vue` | 机构审核页 |
| `frontend/admin/src/router/index.ts` · `layouts/MainLayout.vue` | 路由 + platform_admin 菜单 |

---

## Task 1: admin_institution_service

**Files:**
- Create: `backend/app/services/admin_institution_service.py`
- Test: `tests/services/test_admin_institution.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_admin_institution.py`：

```python
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services import admin_institution_service as svc
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_create_institution_pending(db_session):
    inst = await svc.create_institution(
        db_session, name="新东方", contact_phone="13800000000",
        province_code="11", city_code="1101", address="海淀区1号")
    assert str(inst.status) == "pending"


@pytest.mark.asyncio
async def test_approve_creates_admin(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    inst2, username, password = await svc.approve_institution(
        db_session, institution_id=inst.id, admin_username=uname)
    assert str(inst2.status) == "active"
    assert username == uname and len(password) >= 8
    # 生成的管理员账号可登录
    user = await admin_auth_service.authenticate(db_session, username=uname, password=password)
    assert user is not None and str(user.role) == "institution_admin"
    assert user.institution_id == inst.id


@pytest.mark.asyncio
async def test_approve_non_pending_rejected(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    await svc.approve_institution(db_session, institution_id=inst.id, admin_username=f"x_{uuid.uuid4().hex[:6]}")
    with pytest.raises(AppError):
        await svc.approve_institution(db_session, institution_id=inst.id, admin_username=f"y_{uuid.uuid4().hex[:6]}")


@pytest.mark.asyncio
async def test_reject_suspends(db_session):
    inst = await svc.create_institution(
        db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    inst2 = await svc.reject_institution(db_session, institution_id=inst.id)
    assert str(inst2.status) == "suspended"


@pytest.mark.asyncio
async def test_list_filter_by_status(db_session):
    a = await svc.create_institution(db_session, name="A", contact_phone="1",
        province_code="11", city_code="1101", address="街")
    b = await svc.create_institution(db_session, name="B", contact_phone="2",
        province_code="11", city_code="1101", address="街")
    await svc.reject_institution(db_session, institution_id=b.id)
    pendings = await svc.list_institutions(db_session, status="pending")
    assert all(str(i.status) == "pending" for i in pendings)
    assert any(i.id == a.id for i in pendings)
    assert all(i.id != b.id for i in pendings)
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_admin_institution.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/admin_institution_service.py`：

```python
"""机构入驻审核 service（D-123，超管侧）。"""
from __future__ import annotations

import random
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution
from app.services import admin_auth_service

_PW_CHARS = string.ascii_letters + string.digits


async def create_institution(
    db: AsyncSession, *, name: str, contact_phone: str,
    province_code: str, city_code: str, address: str,
) -> Institution:
    inst = Institution(
        id=uuid.uuid4(), name=name, contact_phone=contact_phone,
        province_code=province_code, city_code=city_code, address=address,
    )
    db.add(inst)
    await db.flush()
    return inst


async def list_institutions(
    db: AsyncSession, *, status: str | None = None
) -> list[Institution]:
    q = select(Institution)
    if status:
        q = q.where(Institution.status == status)
    q = q.order_by(Institution.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def _get(db: AsyncSession, institution_id: uuid.UUID) -> Institution:
    inst = (await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )).scalar_one_or_none()
    if inst is None:
        raise AppError(code=404, message="机构不存在")
    return inst


async def approve_institution(
    db: AsyncSession, *, institution_id: uuid.UUID, admin_username: str
) -> tuple[Institution, str, str]:
    inst = await _get(db, institution_id)
    if str(inst.status) != "pending":
        raise AppError(code=400, message="仅待审核(pending)机构可通过")
    inst.status = "active"  # type: ignore[assignment]
    password = "".join(random.choices(_PW_CHARS, k=10))
    await admin_auth_service.create_institution_admin(
        db, username=admin_username, password=password, institution_id=inst.id)
    await db.flush()
    return inst, admin_username, password


async def reject_institution(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> Institution:
    inst = await _get(db, institution_id)
    inst.status = "suspended"  # type: ignore[assignment]
    await db.flush()
    return inst
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_admin_institution.py -p no:randomly -q`
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_institution_service.py tests/services/test_admin_institution.py
git commit -m "feat(admin): 机构入驻审核 service（建/列/通过开账号/拒绝）"
```

---

## Task 2: schemas + API

**Files:**
- Modify: `backend/app/schemas/institution.py`, `backend/app/api/v1/admin.py`
- Test: `tests/api/test_admin_institution.py`

- [ ] **Step 1: schemas**

在 `backend/app/schemas/institution.py` 末尾加：

```python
class AdminInstitutionCreate(BaseModel):
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str


class AdminInstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str
    status: str
    created_at: dt.datetime


class ApproveInstitutionRequest(BaseModel):
    admin_username: str


class ApproveInstitutionResult(BaseModel):
    institution_id: uuid.UUID
    admin_username: str
    password: str
```

注：`ConfigDict` 已在该文件 import（D-120 用过）；若未，补 `from pydantic import BaseModel, ConfigDict`。

- [ ] **Step 2: 写失败 api 测试**

`tests/api/test_admin_institution.py`：

```python
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _platform_admin(client, username):
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password="pw123456")
        await s.commit()
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_create_list_approve_flow(client):
    h = await _platform_admin(client, f"pa_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/admin/institutions", headers=h, json={
        "name": "机构X", "contact_phone": "138", "province_code": "11",
        "city_code": "1101", "address": "街"})
    assert r.status_code == 200
    inst_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "pending"

    rows = (await client.get("/api/v1/admin/institutions?status=pending", headers=h)).json()["data"]
    assert any(i["id"] == inst_id for i in rows)

    uname = f"ia_{uuid.uuid4().hex[:6]}"
    r = await client.post(f"/api/v1/admin/institutions/{inst_id}/approve",
                          headers=h, json={"admin_username": uname})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["admin_username"] == uname and len(data["password"]) >= 8

    # 新机构管理员能登录
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": uname, "password": data["password"]})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reject(client):
    h = await _platform_admin(client, f"pa_{uuid.uuid4().hex[:6]}")
    inst_id = (await client.post("/api/v1/admin/institutions", headers=h, json={
        "name": "Y", "contact_phone": "1", "province_code": "11",
        "city_code": "1101", "address": "街"})).json()["data"]["id"]
    r = await client.post(f"/api/v1/admin/institutions/{inst_id}/reject", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "suspended"


@pytest.mark.asyncio
async def test_institution_admin_forbidden(client):
    # institution_admin 不能访问超管机构审核
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        uname = f"ia_{uuid.uuid4().hex[:6]}"
        await admin_auth_service.create_institution_admin(
            s, username=uname, password="pw123456", institution_id=inst.id)
        await s.commit()
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": uname, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = await client.get("/api/v1/admin/institutions", headers=h)
    assert r.status_code == 403
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_admin_institution.py -p no:randomly -q`
Expected: FAIL（endpoint 不存在）。

- [ ] **Step 4: 加 API**

在 `backend/app/api/v1/admin.py`：

import 区加：
```python
from app.schemas.institution import (
    AdminInstitutionCreate, AdminInstitutionOut,
    ApproveInstitutionRequest, ApproveInstitutionResult,
)
```
并把 `admin_institution_service` 加入 `from app.services import (...)` 集中导入块。

文件末尾加：

```python
@router.post("/institutions", response_model=BaseResponse[AdminInstitutionOut])
async def admin_create_institution(body: AdminInstitutionCreate, db: DbDep, admin: AdminDep):
    inst = await admin_institution_service.create_institution(
        db, name=body.name, contact_phone=body.contact_phone,
        province_code=body.province_code, city_code=body.city_code, address=body.address)
    await db.commit()
    return make_ok(AdminInstitutionOut.model_validate(inst))


@router.get("/institutions", response_model=BaseResponse[list[AdminInstitutionOut]])
async def admin_list_institutions(db: DbDep, admin: AdminDep, status: str | None = None):
    rows = await admin_institution_service.list_institutions(db, status=status)
    return make_ok([AdminInstitutionOut.model_validate(i) for i in rows])


@router.post("/institutions/{institution_id}/approve",
             response_model=BaseResponse[ApproveInstitutionResult])
async def admin_approve_institution(
    institution_id: uuid.UUID, body: ApproveInstitutionRequest, db: DbDep, admin: AdminDep,
):
    inst, username, password = await admin_institution_service.approve_institution(
        db, institution_id=institution_id, admin_username=body.admin_username)
    await db.commit()
    return make_ok(ApproveInstitutionResult(
        institution_id=inst.id, admin_username=username, password=password))


@router.post("/institutions/{institution_id}/reject", response_model=BaseResponse[AdminInstitutionOut])
async def admin_reject_institution(institution_id: uuid.UUID, db: DbDep, admin: AdminDep):
    inst = await admin_institution_service.reject_institution(db, institution_id=institution_id)
    await db.commit()
    return make_ok(AdminInstitutionOut.model_validate(inst))
```

注：确认 admin.py 顶部已有 `DbDep`（若无则 `DbDep = Annotated[AsyncSession, Depends(get_db)]`，admin.py 现有 DbDep 见文件）。`make_ok`/`BaseResponse`/`uuid` 已 import。

- [ ] **Step 5: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_admin_institution.py -p no:randomly -q`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/admin.py tests/api/test_admin_institution.py
git commit -m "feat(admin): 机构入驻审核 API（建/列/通过/拒绝 + 403 隔离）"
```

---

## Task 3: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 8 测试全过；已知偶发污染项若红，隔离复跑确认通过。

---

## Task 4: admin web 机构审核页

**Files:**
- Modify: `frontend/admin/src/api/admin.ts`, `router/index.ts`, `layouts/MainLayout.vue`
- Create: `frontend/admin/src/views/Institutions.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/admin.ts` 末尾加（`request`/`unwrap` 导入照抄文件现有风格）：

```typescript
export interface AdminInstitution {
  id: string; name: string; contact_phone: string
  province_code: string; city_code: string; address: string
  status: string; created_at: string
}

export function createInstitution(data: {
  name: string; contact_phone: string; province_code: string; city_code: string; address: string
}): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post('/admin/institutions', data))
}
export function listInstitutions(status?: string): Promise<AdminInstitution[]> {
  const q = status ? `?status=${status}` : ''
  return unwrap<AdminInstitution[]>(request.get(`/admin/institutions${q}`))
}
export function approveInstitution(id: string, adminUsername: string): Promise<{ institution_id: string; admin_username: string; password: string }> {
  return unwrap(request.post(`/admin/institutions/${id}/approve`, { admin_username: adminUsername }))
}
export function rejectInstitution(id: string): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post(`/admin/institutions/${id}/reject`))
}
```

> 实现者注意：若 `admin.ts` 未导出 `unwrap`，从 `./request` 引入（见 `api/institution.ts` 的写法）。

- [ ] **Step 2: 机构审核页**

`frontend/admin/src/views/Institutions.vue`：

```vue
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createInstitution, listInstitutions, approveInstitution, rejectInstitution,
  type AdminInstitution,
} from '../api/admin'

const form = reactive({ name: '', contact_phone: '', province_code: '', city_code: '', address: '' })
const filter = ref('')
const rows = ref<AdminInstitution[]>([])

async function load() { rows.value = await listInstitutions(filter.value || undefined) }

async function submit() {
  if (!form.name) { ElMessage.warning('请填机构名称'); return }
  await createInstitution({ ...form })
  ElMessage.success('已录入（待审核）')
  Object.assign(form, { name: '', contact_phone: '', province_code: '', city_code: '', address: '' })
  await load()
}

async function approve(row: AdminInstitution) {
  const { value: uname } = await ElMessageBox.prompt('为该机构设置管理员登录用户名', '通过审核', {
    inputPattern: /.{3,}/, inputErrorMessage: '至少 3 个字符',
  })
  const r = await approveInstitution(row.id, uname)
  await ElMessageBox.alert(
    `用户名：${r.admin_username}\n初始密码：${r.password}\n请复制并线下转交机构，本密码仅此一次显示。`,
    '机构账号已开通', { confirmButtonText: '我已复制' })
  await load()
}

async function reject(row: AdminInstitution) {
  await ElMessageBox.confirm(`确认拒绝「${row.name}」？将置为 suspended。`, '提示', { type: 'warning' })
  await rejectInstitution(row.id)
  ElMessage.success('已拒绝')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">机构审核</h2>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="省编码"><el-input v-model="form.province_code" style="width: 100px" /></el-form-item>
        <el-form-item label="市编码"><el-input v-model="form.city_code" style="width: 100px" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item><el-button type="primary" @click="submit">录入待审核机构</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-select v-model="filter" placeholder="全部状态" clearable style="width: 160px; margin-bottom: 12px" @change="load">
      <el-option label="待审核" value="pending" />
      <el-option label="已通过" value="active" />
      <el-option label="已拒绝/冻结" value="suspended" />
    </el-select>

    <el-table :data="rows" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="contact_phone" label="电话" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="created_at" label="申请时间">
        <template #default="{ row }">{{ row.created_at.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button text type="primary" @click="approve(row)">通过</el-button>
            <el-button text type="danger" @click="reject(row)">拒绝</el-button>
          </template>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
</style>
```

- [ ] **Step 3: 路由 + 菜单**

`router/index.ts` children 内（platform_admin 页那批里，如 essay-templates 之后）加：

```typescript
        { path: 'institutions', name: 'institutions', component: () => import('../views/Institutions.vue') },
```

`layouts/MainLayout.vue` 的 platform_admin 分支（`v-else` 内）加：

```html
          <el-menu-item index="/institutions">机构审核</el-menu-item>
```

- [ ] **Step 4: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add frontend/admin/src/api/admin.ts frontend/admin/src/views/Institutions.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(admin-web): 机构审核页（录入/筛选/通过开账号/拒绝）"
```

---

## Task 5: 归档 D-123 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部按既有格式加 D-123（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-120、需求 §5.1）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` 超管侧加一行：机构审核（录入→通过开账号→拒绝）；注明「拒绝=suspended（无 rejected 枚举）」「机构公开自助入驻申请端后续」。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-onboarding-review.md
git commit -m "docs: 归档 D-123 入驻审核（超管侧）"
```

---

## Self-Review 结论

- **Spec 覆盖**：create/list/approve/reject service→Task1；schemas+4 endpoints+403→Task2；回归→Task3；admin 审核页→Task4；归档→Task5。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码；前端 `unwrap` 引入处点名参照 `api/institution.ts`。
- **类型一致**：`create_institution(name,contact_phone,province_code,city_code,address)`、`approve_institution(institution_id,admin_username)→(inst,username,password)`、`reject_institution(institution_id)`、`list_institutions(status=)` 在 service/api/test 三处一致；`AdminInstitutionOut`/`ApproveInstitutionResult` 字段在 api 返回、前端 interface、测试断言一致；拒绝→"suspended" 三处一致。
