# 机构端切片五：批量续费（3b，D-124）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构管理员后台列出名下有会员的学生（可按近 N 天到期筛），勾选批量续费指定月数（dev-mock 即付），各学生会员到期日延长。

**Architecture:** 复用 `membership_service.activate_membership` 的 renew 分支（同档位从 max(到期,now) 延长）。逐学生造已支付 renew Order。零迁移、无真实扣款。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 测试夹具：service 用本地 `db_session`（`_async_session_factory`），见 `tests/services/test_institution_purchase.py`；api 用本地 `client` + `/api/v1/admin/auth/login`（机构管理员用 `create_institution_admin` 种子），见 `tests/api/test_institution_purchase.py`。
- `activate_membership(db, *, order)` 要求 order 已 flush 出 id（renew 分支也用 order_id 发通知）。
- renew 生效前提：该生有 `is_active=True` 且 `tier==order.tier` 的 membership；本切片 tier 取自该生现有会员，故必然命中 renew 分支。
- 金额单价复用 `institution_purchase_service._TIER_MONTHLY_FEN`。
- 统一响应 `make_ok` + `BaseResponse[T]`；鉴权 `InstAdminDep`（institution.py）。
- 本切片**无迁移、无付费调用**，纯 DB。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/institution_renew_service.py` | list_renewable_students / batch_renew |
| `backend/app/schemas/institution.py` | +续费相关 schemas |
| `backend/app/api/v1/institution.py` | +续费 2 endpoints |
| `frontend/admin/src/api/institution.ts` | +续费 2 接口 |
| `frontend/admin/src/views/InstitutionRenew.vue` | 批量续费页 |
| `frontend/admin/src/router/index.ts` · `layouts/MainLayout.vue` | 路由 + 菜单 |

---

## Task 1: institution_renew_service

**Files:**
- Create: `backend/app/services/institution_renew_service.py`
- Test: `tests/services/test_institution_renew.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_renew.py`：

```python
import datetime as dt
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import institution_renew_service as svc
from app.services import membership_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    return inst


async def _student_with_membership(s, inst_id, *, tier="pro", days_to_expire=10):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student", nickname="学生"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(
        id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
        expires_at=now + dt.timedelta(days=days_to_expire), is_active=True))
    await s.flush()
    return uid


async def _student_no_membership(s, inst_id):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_list_renewable_only_members(db_session):
    inst = await _inst(db_session)
    m = await _student_with_membership(db_session, inst.id)
    await _student_no_membership(db_session, inst.id)
    rows = await svc.list_renewable_students(db_session, institution_id=inst.id)
    ids = [r[0] for r in rows]
    assert m in ids and len(rows) == 1


@pytest.mark.asyncio
async def test_list_expiring_filter(db_session):
    inst = await _inst(db_session)
    near = await _student_with_membership(db_session, inst.id, days_to_expire=10)
    await _student_with_membership(db_session, inst.id, days_to_expire=200)
    rows = await svc.list_renewable_students(db_session, institution_id=inst.id, expiring_days=30)
    ids = [r[0] for r in rows]
    assert near in ids and len(rows) == 1


@pytest.mark.asyncio
async def test_batch_renew_extends_expiry(db_session):
    inst = await _inst(db_session)
    sid = await _student_with_membership(db_session, inst.id, tier="pro", days_to_expire=10)
    before = (await membership_service.get_active_membership(db_session, user_id=sid)).expires_at
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await db_session.flush()
    res = await svc.batch_renew(db_session, institution_id=inst.id,
                                student_ids=[sid], duration_months=6, operator_id=admin)
    assert res["renewed_count"] == 1
    assert res["total_amount_fen"] == 3000 * 6
    after = (await membership_service.get_active_membership(db_session, user_id=sid)).expires_at
    assert after > before


@pytest.mark.asyncio
async def test_batch_renew_skips_invalid(db_session):
    inst = await _inst(db_session)
    other = await _inst(db_session, "B")
    no_mem = await _student_no_membership(db_session, inst.id)
    b_member = await _student_with_membership(db_session, other.id)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await db_session.flush()
    res = await svc.batch_renew(db_session, institution_id=inst.id,
                                student_ids=[no_mem, b_member], duration_months=1, operator_id=admin)
    assert res["renewed_count"] == 0
    assert set(res["skipped"]) == {no_mem, b_member}
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_renew.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/institution_renew_service.py`：

```python
"""机构批量续费 service（D-124）。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Student, User
from app.models.d2_payments import Membership, Order
from app.services import membership_service
from app.services.institution_purchase_service import _TIER_MONTHLY_FEN


async def list_renewable_students(
    db: AsyncSession, *, institution_id: uuid.UUID, expiring_days: int | None = None
) -> list[tuple[uuid.UUID, str | None, str, dt.datetime]]:
    q = (
        select(Student.id, User.nickname, Membership.tier, Membership.expires_at)
        .join(User, User.id == Student.id)
        .join(Membership, (Membership.user_id == Student.id) & (Membership.is_active.is_(True)))
        .where(Student.institution_id == institution_id)
    )
    if expiring_days is not None:
        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=expiring_days)
        q = q.where(Membership.expires_at <= cutoff)
    q = q.order_by(Membership.expires_at.asc())
    rows = (await db.execute(q)).all()
    return [(sid, nickname, str(tier), expires_at) for sid, nickname, tier, expires_at in rows]


async def batch_renew(
    db: AsyncSession, *, institution_id: uuid.UUID,
    student_ids: list[uuid.UUID], duration_months: int, operator_id: uuid.UUID,
) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    renewed_count = 0
    total_amount_fen = 0
    skipped: list[uuid.UUID] = []

    for sid in student_ids:
        student = await db.get(Student, sid)
        if student is None or student.institution_id != institution_id:
            skipped.append(sid)
            continue
        membership = await membership_service.get_active_membership(db, user_id=sid)
        if membership is None:
            skipped.append(sid)
            continue
        tier = str(membership.tier)
        amount = _TIER_MONTHLY_FEN.get(tier, 0) * duration_months
        order = Order(
            id=uuid.uuid4(),
            order_no=f"RNW{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
            payer_id=operator_id,
            beneficiary_id=sid,
            order_type="renew",  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            duration_months=duration_months,
            amount_fen=amount,
            status="paid",  # type: ignore[arg-type]
        )
        db.add(order)
        await db.flush()
        await membership_service.activate_membership(db, order=order)
        renewed_count += 1
        total_amount_fen += amount

    return {"renewed_count": renewed_count, "total_amount_fen": total_amount_fen, "skipped": skipped}
```

注：`_TIER_MONTHLY_FEN` 从 `institution_purchase_service` import 复用；`order_no` 前缀 RNW 区别于采购激活的 ACT。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_renew.py -p no:randomly -q`
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_renew_service.py tests/services/test_institution_renew.py
git commit -m "feat(institution): 批量续费 service（可续学生列表 + batch_renew 延长会员）"
```

---

## Task 2: schemas + API

**Files:**
- Modify: `backend/app/schemas/institution.py`, `backend/app/api/v1/institution.py`
- Test: `tests/api/test_institution_renew.py`

- [ ] **Step 1: schemas**

在 `backend/app/schemas/institution.py` 末尾加：

```python
class RenewableStudentOut(BaseModel):
    student_id: uuid.UUID
    nickname: str | None = None
    tier: str
    expires_at: dt.datetime


class BatchRenewRequest(BaseModel):
    student_ids: list[uuid.UUID]
    duration_months: int


class BatchRenewResult(BaseModel):
    renewed_count: int
    total_amount_fen: int
    skipped: list[uuid.UUID]
```

- [ ] **Step 2: 写失败 api 测试**

`tests/api/test_institution_renew.py`：

```python
import datetime as dt
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _setup(username, inst_name="机构A"):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        # 一个有会员的学生
        sid = uuid.uuid4()
        s.add(User(id=sid, openid=f"o:{sid}", role="student", nickname="学生"))
        await s.flush()
        s.add(Student(id=sid, institution_id=inst.id))
        now = dt.datetime.now(dt.timezone.utc)
        s.add(Membership(id=uuid.uuid4(), user_id=sid, tier="pro", started_at=now,
                         expires_at=now + dt.timedelta(days=10), is_active=True))
        await s.commit()
        return inst.id, sid


async def _login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_list_and_batch_renew(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    _, sid = await _setup(uname)
    h = await _login(client, uname)

    rows = (await client.get("/api/v1/institution/renewable-students", headers=h)).json()["data"]
    assert any(r["student_id"] == str(sid) for r in rows)
    before = next(r for r in rows if r["student_id"] == str(sid))["expires_at"]

    r = await client.post("/api/v1/institution/batch-renew", headers=h,
                          json={"student_ids": [str(sid)], "duration_months": 6})
    assert r.status_code == 200
    assert r.json()["data"]["renewed_count"] == 1

    rows2 = (await client.get("/api/v1/institution/renewable-students", headers=h)).json()["data"]
    after = next(r for r in rows2 if r["student_id"] == str(sid))["expires_at"]
    assert after > before
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_renew.py -p no:randomly -q`
Expected: FAIL（endpoint 不存在）。

- [ ] **Step 4: 加 API**

在 `backend/app/api/v1/institution.py`：import 区扩 institution schema import 加 `BatchRenewRequest, BatchRenewResult, RenewableStudentOut`；services import 加 `institution_renew_service`。

文件末尾加：

```python
@router.get("/renewable-students", response_model=BaseResponse[list[RenewableStudentOut]])
async def list_renewable_students(db: DbDep, admin: InstAdminDep, expiring_days: int | None = None):
    inst_id = _require_inst(admin)
    rows = await institution_renew_service.list_renewable_students(
        db, institution_id=inst_id, expiring_days=expiring_days)
    return make_ok([
        RenewableStudentOut(student_id=sid, nickname=nick, tier=tier, expires_at=exp)
        for sid, nick, tier, exp in rows
    ])


@router.post("/batch-renew", response_model=BaseResponse[BatchRenewResult])
async def batch_renew(body: BatchRenewRequest, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    res = await institution_renew_service.batch_renew(
        db, institution_id=inst_id, student_ids=body.student_ids,
        duration_months=body.duration_months, operator_id=admin.id)
    await db.commit()
    return make_ok(BatchRenewResult(**res))
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_renew.py -p no:randomly -q`
Expected: 1 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py tests/api/test_institution_renew.py
git commit -m "feat(institution): 批量续费 API（可续学生列表 + batch-renew）"
```

---

## Task 3: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 5 测试全过；已知偶发污染项若红，隔离复跑确认通过。

---

## Task 4: admin web 批量续费页

**Files:**
- Modify: `frontend/admin/src/api/institution.ts`, `router/index.ts`, `layouts/MainLayout.vue`
- Create: `frontend/admin/src/views/InstitutionRenew.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/institution.ts` 末尾加：

```typescript
export interface RenewableStudent {
  student_id: string; nickname: string | null; tier: string; expires_at: string
}

export function listRenewableStudents(expiringDays?: number): Promise<RenewableStudent[]> {
  const q = expiringDays != null ? `?expiring_days=${expiringDays}` : ''
  return unwrap<RenewableStudent[]>(request.get(`/institution/renewable-students${q}`))
}
export function batchRenew(studentIds: string[], durationMonths: number): Promise<{ renewed_count: number; total_amount_fen: number; skipped: string[] }> {
  return unwrap(request.post('/institution/batch-renew', { student_ids: studentIds, duration_months: durationMonths }))
}
```

- [ ] **Step 2: 批量续费页**

`frontend/admin/src/views/InstitutionRenew.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listRenewableStudents, batchRenew, type RenewableStudent } from '../api/institution'

const rows = ref<RenewableStudent[]>([])
const selected = ref<RenewableStudent[]>([])
const onlyExpiring = ref(true)
const months = ref(6)

async function load() {
  rows.value = await listRenewableStudents(onlyExpiring.value ? 30 : undefined)
}

async function renew() {
  if (!selected.value.length) return
  const ids = selected.value.map((r) => r.student_id)
  const res = await batchRenew(ids, months.value)
  ElMessage.success(`续费 ${res.renewed_count} 人，跳过 ${res.skipped.length} 人，合计 ¥${(res.total_amount_fen / 100).toFixed(2)}`)
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">批量续费</h2>
    <el-card style="margin-bottom: 16px">
      <el-checkbox v-model="onlyExpiring" @change="load">仅看近 30 天到期</el-checkbox>
      <span style="margin-left: 24px">续费月数：</span>
      <el-input-number v-model="months" :min="1" />
      <el-button type="primary" style="margin-left: 16px" :disabled="!selected.length" @click="renew">
        批量续费（dev-mock 即付）
      </el-button>
    </el-card>
    <el-table :data="rows" border @selection-change="(v) => (selected = v)">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="tier" label="档位" />
      <el-table-column label="到期日">
        <template #default="{ row }">{{ row.expires_at.slice(0, 10) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
</style>
```

- [ ] **Step 3: 路由 + 菜单**

`router/index.ts` children 内（institution/purchases 之后）加：

```typescript
        { path: 'institution/renew', name: 'institution-renew', component: () => import('../views/InstitutionRenew.vue'), meta: { roles: ['institution_admin'] } },
```

`layouts/MainLayout.vue` 的 institution_admin 分支内（学生采购之后）加：

```html
          <el-menu-item index="/institution/renew">批量续费</el-menu-item>
```

- [ ] **Step 4: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add frontend/admin/src/api/institution.ts frontend/admin/src/views/InstitutionRenew.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(institution-web): 批量续费页（到期筛选/勾选/批量续费）"
```

---

## Task 5: 归档 D-124 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部按既有格式加 D-124（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-122、需求 §5B.5）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` 机构端表加 M7（批量续费：列可续学生→批量续费→到期延后）。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-batch-renew.md
git commit -m "docs: 归档 D-124 批量续费（3b）"
```

---

## Self-Review 结论

- **Spec 覆盖**：list/batch_renew service→Task1；schemas+2 endpoints→Task2；回归→Task3；admin 续费页→Task4；归档→Task5。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码。
- **类型一致**：`list_renewable_students(institution_id,expiring_days)→list[(sid,nick,tier,exp)]`、`batch_renew(institution_id,student_ids,duration_months,operator_id)→{renewed_count,total_amount_fen,skipped}` 在 service/api/test 三处一致；`RenewableStudentOut`/`BatchRenewResult` 字段在 api 返回、前端 interface、测试断言一致；renew Order order_type="renew" + tier=该生现有档位，命中 activate_membership renew 分支。
