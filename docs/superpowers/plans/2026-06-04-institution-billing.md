# 机构端切片六：机构账单导出（3c，D-125）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构管理员后台「账单」页查看本机构采购+续费合并账单（时间倒序），一键导出 CSV。

**Architecture:** 后端合并 `institution_purchases`（采购）与 `orders.order_type='renew'` 且付款人属本机构（续费）成统一账单条目。前端表格 + 客户端 Blob 导出 CSV。零迁移、无付费。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 测试夹具：service 用本地 `db_session`（`_async_session_factory`），见 `tests/services/test_institution_renew.py`；api 用本地 `client` + `/api/v1/admin/auth/login`，见 `tests/api/test_institution_renew.py`。
- 统一响应 `make_ok` + `BaseResponse[T]`；鉴权 `InstAdminDep`（institution.py）。
- 续费单经 `payer_id → users.institution_id` 关联机构；采购单直接有 `institution_id`。
- 本切片**无迁移、无付费调用**，纯 DB。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/institution_billing_service.py` | list_bills（合并采购+续费） |
| `backend/app/schemas/institution.py` | +BillItemOut |
| `backend/app/api/v1/institution.py` | +GET /bills |
| `frontend/admin/src/api/institution.ts` | +listBills |
| `frontend/admin/src/views/InstitutionBills.vue` | 账单页 + CSV 导出 |
| `frontend/admin/src/router/index.ts` · `layouts/MainLayout.vue` | 路由 + 菜单 |

---

## Task 1: institution_billing_service

**Files:**
- Create: `backend/app/services/institution_billing_service.py`
- Test: `tests/services/test_institution_billing.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_billing.py`：

```python
import datetime as dt
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import institution_billing_service as svc
from app.services import institution_purchase_service, institution_renew_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst_admin(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    admin = uuid.uuid4()
    s.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await s.flush()
    return inst.id, admin


async def _student_member(s, inst_id, *, tier="pro"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
                     expires_at=now + dt.timedelta(days=10), is_active=True))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_list_bills_merges_purchase_and_renew(db_session):
    inst_id, admin = await _inst_admin(db_session)
    await institution_purchase_service.create_purchase(
        db_session, institution_id=inst_id, created_by=admin,
        tier="pro", duration_months=6, quantity=2)
    sid = await _student_member(db_session, inst_id, tier="pro")
    await institution_renew_service.batch_renew(
        db_session, institution_id=inst_id, student_ids=[sid],
        duration_months=3, operator_id=admin)

    bills = await svc.list_bills(db_session, institution_id=inst_id)
    types = [b["type"] for b in bills]
    assert "采购" in types and "续费" in types
    # 倒序：date 非递增
    dates = [b["date"] for b in bills]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_list_bills_isolated(db_session):
    a_id, a_admin = await _inst_admin(db_session, "A")
    b_id, b_admin = await _inst_admin(db_session, "B")
    await institution_purchase_service.create_purchase(
        db_session, institution_id=b_id, created_by=b_admin,
        tier="basic", duration_months=1, quantity=1)
    sid = await _student_member(db_session, b_id, tier="basic")
    await institution_renew_service.batch_renew(
        db_session, institution_id=b_id, student_ids=[sid],
        duration_months=1, operator_id=b_admin)

    bills_a = await svc.list_bills(db_session, institution_id=a_id)
    assert bills_a == []
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_billing.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/institution_billing_service.py`：

```python
"""机构账单 service（D-125）：采购 + 续费 合并账单。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d2_payments import InstitutionPurchase, Order


async def list_bills(db: AsyncSession, *, institution_id: uuid.UUID) -> list[dict]:
    bills: list[dict] = []

    purchases = (await db.execute(
        select(InstitutionPurchase)
        .where(InstitutionPurchase.institution_id == institution_id)
    )).scalars().all()
    for p in purchases:
        bills.append({
            "date": p.created_at,
            "type": "采购",
            "summary": f"{p.tier} × {p.quantity}（{p.duration_months}月）",
            "amount_fen": p.amount_fen,
        })

    admin_ids = select(User.id).where(User.institution_id == institution_id)
    renews = (await db.execute(
        select(Order)
        .where(Order.order_type == "renew", Order.payer_id.in_(admin_ids))
    )).scalars().all()
    for o in renews:
        bills.append({
            "date": o.created_at,
            "type": "续费",
            "summary": f"{o.tier} 续费 {o.duration_months}月",
            "amount_fen": o.amount_fen,
        })

    bills.sort(key=lambda b: b["date"], reverse=True)
    return bills
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_billing.py -p no:randomly -q`
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_billing_service.py tests/services/test_institution_billing.py
git commit -m "feat(institution): 机构账单 service（采购+续费合并，时间倒序）"
```

---

## Task 2: schemas + API

**Files:**
- Modify: `backend/app/schemas/institution.py`, `backend/app/api/v1/institution.py`
- Test: `tests/api/test_institution_billing.py`

- [ ] **Step 1: schemas**

在 `backend/app/schemas/institution.py` 末尾加：

```python
class BillItemOut(BaseModel):
    date: dt.datetime
    type: str
    summary: str
    amount_fen: int
```

- [ ] **Step 2: 写失败 api 测试**

`tests/api/test_institution_billing.py`：

```python
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.services import admin_auth_service, institution_purchase_service


async def _setup(username, inst_name="机构A"):
    from app.models.d1_users import Institution
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        admin = await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.flush()
        await institution_purchase_service.create_purchase(
            s, institution_id=inst.id, created_by=admin.id,
            tier="pro", duration_months=6, quantity=1)
        await s.commit()
        return inst.id


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_list_bills_api(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup(uname)
    h = await _login(client, uname)
    r = await client.get("/api/v1/institution/bills", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(b["type"] == "采购" for b in data)


@pytest.mark.asyncio
async def test_platform_admin_forbidden(client):
    uname = f"pa_{uuid.uuid4().hex[:6]}"
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=uname, password="pw123456")
        await s.commit()
    h = await _login(client, uname)
    r = await client.get("/api/v1/institution/bills", headers=h)
    assert r.status_code == 403
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_billing.py -p no:randomly -q`
Expected: FAIL（endpoint 不存在）。

- [ ] **Step 4: 加 API**

在 `backend/app/api/v1/institution.py`：institution schema import 加 `BillItemOut`；services import 加 `institution_billing_service`。

文件末尾加：

```python
@router.get("/bills", response_model=BaseResponse[list[BillItemOut]])
async def list_bills(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_billing_service.list_bills(db, institution_id=inst_id)
    return make_ok([BillItemOut(**r) for r in rows])
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_billing.py -p no:randomly -q`
Expected: 2 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py tests/api/test_institution_billing.py
git commit -m "feat(institution): 机构账单 API（GET /bills + 403 隔离）"
```

---

## Task 3: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 4 测试全过；已知偶发污染项若红，隔离复跑确认通过。

---

## Task 4: admin web 账单页 + CSV 导出

**Files:**
- Modify: `frontend/admin/src/api/institution.ts`, `router/index.ts`, `layouts/MainLayout.vue`
- Create: `frontend/admin/src/views/InstitutionBills.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/institution.ts` 末尾加：

```typescript
export interface BillItem { date: string; type: string; summary: string; amount_fen: number }

export function listBills(): Promise<BillItem[]> {
  return unwrap<BillItem[]>(request.get('/institution/bills'))
}
```

- [ ] **Step 2: 账单页**

`frontend/admin/src/views/InstitutionBills.vue`：

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listBills, type BillItem } from '../api/institution'

const rows = ref<BillItem[]>([])
const total = computed(() => rows.value.reduce((s, b) => s + b.amount_fen, 0))

async function load() { rows.value = await listBills() }

function exportCsv() {
  const header = '日期,类型,明细,金额(元)'
  const lines = rows.value.map((b) =>
    `${b.date.slice(0, 10)},${b.type},"${b.summary}",${(b.amount_fen / 100).toFixed(2)}`)
  const csv = '﻿' + [header, ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `机构账单_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">账单</h2>
    <div class="bar">
      <span>合计：¥ {{ (total / 100).toFixed(2) }}</span>
      <el-button type="primary" :disabled="!rows.length" @click="exportCsv">导出 CSV</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column label="日期">
        <template #default="{ row }">{{ row.date.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="100" />
      <el-table-column prop="summary" label="明细" />
      <el-table-column label="金额(元)" width="140">
        <template #default="{ row }">{{ (row.amount_fen / 100).toFixed(2) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
</style>
```

- [ ] **Step 3: 路由 + 菜单**

`router/index.ts` children 内（institution/renew 之后）加：

```typescript
        { path: 'institution/bills', name: 'institution-bills', component: () => import('../views/InstitutionBills.vue'), meta: { roles: ['institution_admin'] } },
```

`layouts/MainLayout.vue` 的 institution_admin 分支内（批量续费之后）加：

```html
          <el-menu-item index="/institution/bills">账单</el-menu-item>
```

- [ ] **Step 4: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add frontend/admin/src/api/institution.ts frontend/admin/src/views/InstitutionBills.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(institution-web): 账单页 + CSV 导出"
```

---

## Task 5: 归档 D-125 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部按既有格式加 D-125（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-122 D-124、需求 §5B.5）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` 机构端表加 M8（账单：查看采购+续费合并账单→导出 CSV）。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-billing.md
git commit -m "docs: 归档 D-125 机构账单导出（3c）"
```

---

## Self-Review 结论

- **Spec 覆盖**：list_bills service→Task1；schemas+endpoint→Task2；回归→Task3；admin 账单页+CSV→Task4；归档→Task5。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码。
- **类型一致**：`list_bills(institution_id)→list[{date,type,summary,amount_fen}]` 在 service/api/test 三处一致；`BillItemOut` 四字段 ↔ 前端 `BillItem` interface ↔ 测试断言一致；续费经 `payer_id in (users where institution_id==X)` 关联，采购经 `institution_id` 直关联。
