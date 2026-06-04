# 机构端切片八：机构会员到期预警通知（D-127）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cron 每日对各机构统计名下近30天到期会员，>0 则给机构管理员发站内通知；机构管理员在 admin web「通知」中心查看。

**Architecture:** 复用 `notification_service.emit(type_="membership")` + 现有 `/notifications/*` API + reminder cron 范式。零迁移、无花钱。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- service 不内部 commit（CLI/测试负责），与 `reminder_service` 一致；`emit` 内部 flush。
- `notification_service.emit(db, *, user_id, type_, title, content, meta=None)`；type 用 `"membership"`（零新枚举）。
- `/notifications/*` 已存在且用 `get_current_user`，admin web 直接复用；响应 `NotificationListOut{items,total,unread_count}`、`UnreadCountOut{count}`、`NotificationOut`（字段以 `app/schemas` 现有为准：含 id/title/content/type/is_read/created_at 等）。
- 测试夹具：service 用本地 `db_session`，见 `tests/services/test_institution_renew.py`。
- 本切片**无迁移、无付费调用**。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/institution_expiry_alert_service.py` | run_expiry_alerts |
| `backend/app/tasks/send_expiry_alerts.py` | CLI cron |
| `frontend/admin/src/api/notifications.ts` | list/markRead/unreadCount |
| `frontend/admin/src/views/Notifications.vue` | 通知中心页 |
| `frontend/admin/src/router/index.ts` · `layouts/MainLayout.vue` | 路由 + 两角色菜单 |

---

## Task 1: institution_expiry_alert_service

**Files:**
- Create: `backend/app/services/institution_expiry_alert_service.py`
- Test: `tests/services/test_institution_expiry_alert.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_expiry_alert.py`：

```python
import datetime as dt
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.models.d9_system import Notification
from app.services import institution_expiry_alert_service as svc


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
    return inst.id


async def _admin(s, inst_id):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="institution_admin", institution_id=inst_id))
    await s.flush()
    return uid


async def _student_expiring(s, inst_id, *, days_to_expire=10, tier="pro"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
                     expires_at=now + dt.timedelta(days=days_to_expire), is_active=True))
    await s.flush()
    return uid


async def _notifs_for(s, user_id):
    return (await s.execute(
        select(Notification).where(Notification.user_id == user_id)
    )).scalars().all()


@pytest.mark.asyncio
async def test_alert_emitted_when_expiring(db_session):
    inst = await _inst(db_session)
    admin = await _admin(db_session, inst)
    await _student_expiring(db_session, inst, days_to_expire=10)
    res = await svc.run_expiry_alerts(db_session, days=30)
    assert res["institutions_notified"] == 1
    assert res["admins_notified"] == 1
    notifs = await _notifs_for(db_session, admin)
    assert len(notifs) == 1
    assert str(notifs[0].type) == "membership"


@pytest.mark.asyncio
async def test_no_alert_when_none_expiring(db_session):
    inst = await _inst(db_session)
    admin = await _admin(db_session, inst)
    await _student_expiring(db_session, inst, days_to_expire=200)
    res = await svc.run_expiry_alerts(db_session, days=30)
    assert res["institutions_notified"] == 0
    assert await _notifs_for(db_session, admin) == []


@pytest.mark.asyncio
async def test_isolated_and_multi_admin(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    a1 = await _admin(db_session, a)
    a2 = await _admin(db_session, a)
    b1 = await _admin(db_session, b)
    await _student_expiring(db_session, a, days_to_expire=5)
    # B 无到期
    res = await svc.run_expiry_alerts(db_session, days=30)
    assert len(await _notifs_for(db_session, a1)) == 1
    assert len(await _notifs_for(db_session, a2)) == 1
    assert await _notifs_for(db_session, b1) == []
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_expiry_alert.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/institution_expiry_alert_service.py`：

```python
"""机构会员到期预警（D-127）：名下学生近 N 天到期 → 站内通知机构管理员。"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Student, User
from app.models.d2_payments import Membership
from app.services import notification_service


async def run_expiry_alerts(db: AsyncSession, *, days: int = 30) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now + dt.timedelta(days=days)

    # 机构管理员按机构分组
    admin_rows = (await db.execute(
        select(User.id, User.institution_id).where(
            User.role == "institution_admin",
            User.institution_id.is_not(None),
        )
    )).all()
    by_inst: dict = {}
    for uid, inst_id in admin_rows:
        by_inst.setdefault(inst_id, []).append(uid)

    institutions_notified = 0
    admins_notified = 0
    for inst_id, admins in by_inst.items():
        student_ids = select(Student.id).where(Student.institution_id == inst_id)
        expiring = (await db.execute(
            select(func.count(func.distinct(Membership.user_id))).where(
                Membership.user_id.in_(student_ids),
                Membership.is_active.is_(True),
                Membership.expires_at.is_not(None),
                Membership.expires_at >= now,
                Membership.expires_at <= cutoff,
            )
        )).scalar_one()
        if expiring <= 0:
            continue
        institutions_notified += 1
        for admin_id in admins:
            await notification_service.emit(
                db, user_id=admin_id, type_="membership",
                title="会员到期预警",
                content=f"您机构有 {expiring} 名学生会员将在 {days} 天内到期，请及时续费。",
            )
            admins_notified += 1

    return {"institutions_notified": institutions_notified, "admins_notified": admins_notified}
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_expiry_alert.py -p no:randomly -q`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_expiry_alert_service.py tests/services/test_institution_expiry_alert.py
git commit -m "feat(institution): 会员到期预警 service（名下近30天到期→通知机构管理员）"
```

---

## Task 2: CLI cron + 后端全量回归

**Files:**
- Create: `backend/app/tasks/send_expiry_alerts.py`

- [ ] **Step 1: 写 CLI**

`backend/app/tasks/send_expiry_alerts.py`（镜像 `send_checkin_reminders.py`）：

```python
"""机构会员到期预警 CLI：供服务器 crontab 每日调用。
用法：DATABASE_URL=... python -m app.tasks.send_expiry_alerts
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import institution_expiry_alert_service


async def _main() -> None:
    async with _async_session_factory() as s:
        res = await institution_expiry_alert_service.run_expiry_alerts(s)
        await s.commit()
        print(f"[expiry-alerts] institutions={res['institutions_notified']} "
              f"admins={res['admins_notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: CLI 可导入校验**

Run: `cd backend && /opt/anaconda3/bin/python -c "import app.tasks.send_expiry_alerts; print('ok')"`
Expected: `ok`。

- [ ] **Step 3: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 全绿；已知偶发污染项隔离复跑确认。

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks/send_expiry_alerts.py
git commit -m "feat(institution): 会员到期预警 CLI cron（send_expiry_alerts）"
```

---

## Task 3: admin web 通知中心

**Files:**
- Create: `frontend/admin/src/api/notifications.ts`, `frontend/admin/src/views/Notifications.vue`
- Modify: `frontend/admin/src/router/index.ts`, `layouts/MainLayout.vue`

- [ ] **Step 1: api 层**

`frontend/admin/src/api/notifications.ts`：

```typescript
import request, { unwrap } from './request'

export interface AdminNotification {
  id: string
  type: string
  title: string
  content: string
  is_read: boolean
  created_at: string
}

export function listNotifications(): Promise<{ items: AdminNotification[]; total: number; unread_count: number }> {
  return unwrap(request.get('/notifications/?limit=50'))
}
export function markRead(id: string): Promise<AdminNotification> {
  return unwrap<AdminNotification>(request.patch(`/notifications/${id}/read`))
}
export function unreadCount(): Promise<{ count: number }> {
  return unwrap(request.get('/notifications/unread-count'))
}
```

> 实现者注意：`AdminNotification` 字段以后端 `NotificationOut` 实际字段为准（打开 `backend/app/schemas/notifications.py` 或 `d9_system` 确认 is_read/read_at 字段名）；若是 `read_at` 而非 `is_read`，相应改 interface 与模板判断。

- [ ] **Step 2: 通知中心页**

`frontend/admin/src/views/Notifications.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotifications, markRead, type AdminNotification } from '../api/notifications'

const rows = ref<AdminNotification[]>([])
const unread = ref(0)

async function load() {
  const r = await listNotifications()
  rows.value = r.items
  unread.value = r.unread_count
}

async function read(n: AdminNotification) {
  if (n.is_read) return
  await markRead(n.id)
  ElMessage.success('已读')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">通知 <span v-if="unread" class="badge">{{ unread }}</span></h2>
    <el-table :data="rows" border>
      <el-table-column prop="title" label="标题" width="180" />
      <el-table-column prop="content" label="内容" />
      <el-table-column label="时间" width="120">
        <template #default="{ row }">{{ row.created_at.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.is_read" type="info">已读</el-tag>
          <el-button v-else text type="primary" @click="read(row)">标为已读</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.badge { background: #f56c6c; color: #fff; border-radius: 10px; padding: 0 8px; font-size: 12px; }
</style>
```

- [ ] **Step 3: 路由 + 菜单（两角色）**

`router/index.ts` children 内加（无 roles 限制，两角色都可访问）：

```typescript
        { path: 'notifications', name: 'notifications', component: () => import('../views/Notifications.vue') },
```

`layouts/MainLayout.vue`：在 institution_admin 分支末尾、以及 platform_admin（v-else）分支末尾，各加：

```html
          <el-menu-item index="/notifications">通知</el-menu-item>
```

- [ ] **Step 4: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功（若 `is_read` 字段名不符报 TS 错，按 Step1 注修正）。

- [ ] **Step 5: Commit**

```bash
git add frontend/admin/src/api/notifications.ts frontend/admin/src/views/Notifications.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(admin-web): 通知中心页（复用 /notifications API，两角色可见）"
```

---

## Task 4: 归档 D-127 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部加 D-127（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-108 D-124、需求 §5B）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md`：dev-mock/cron 节加 `send_expiry_alerts` 每日 cron；机构端表加 M9（admin web 通知中心查看到期预警）。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-expiry-alert.md
git commit -m "docs: 归档 D-127 机构会员到期预警通知"
```

---

## Self-Review 结论

- **Spec 覆盖**：预警 service→Task1；CLI+回归→Task2；admin 通知中心→Task3；归档→Task4。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码；`is_read` 字段名差异已给应对说明。
- **类型一致**：`run_expiry_alerts(days=)→{institutions_notified,admins_notified}` 在 service/CLI/test 一致；emit type="membership"（零新枚举）；前端 `AdminNotification` 字段以后端 NotificationOut 为准（Step1 注校验）。
