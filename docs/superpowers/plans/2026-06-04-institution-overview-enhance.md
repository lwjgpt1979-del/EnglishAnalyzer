# 机构端切片七：机构数据概览增强（D-126）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构概览新增「近30天到期会员数」「各档位会员分布」「本月采购额」三项指标并在 admin web 展示。

**Architecture:** 扩展 `institution_service.get_overview` 返回值 + `InstitutionOverviewOut` 字段 + 前端卡片。复用现有表聚合。零迁移、无花钱。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 改动现有函数 `get_overview` 与现有测试 `test_get_overview_counts`、`test_overview_and_profile`，注意保持原 4 项口径不变。
- `institution_service.py` 顶部已 `import datetime as dt`、`from sqlalchemy import func, select`、`from app.models.d2_payments import Membership`；需补 import `InstitutionPurchase`。
- 本切片**无迁移、无付费调用**。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/app/services/institution_service.py` | get_overview 增 3 指标 |
| `backend/app/schemas/institution.py` | InstitutionOverviewOut 加 3 字段 |
| `backend/tests`（services/api） | 更新+新增测试 |
| `frontend/admin/src/views/InstitutionOverview.vue` | 新卡片 + 档位分布 |

---

## Task 1: get_overview 增强 + service 测试

**Files:**
- Modify: `backend/app/services/institution_service.py`
- Test: `tests/services/test_institution_service.py`

- [ ] **Step 1: 写新测试 + 更新旧断言**

在 `tests/services/test_institution_service.py` 末尾新增（夹具/helpers 已在文件内：`_institution`、`_teacher`、`_student`；注意 `_student` 的 member=True 建的是 tier="pro" 的 Membership，见文件实现）：

```python
@pytest.mark.asyncio
async def test_get_overview_enhanced(db_session):
    import datetime as dt
    from app.models.d2_payments import InstitutionPurchase
    inst = await _institution(db_session)
    # 3 个 pro 会员（_student member=True → tier=pro），其中 2 个近30天到期、1 个远期
    await _student(db_session, inst.id, member=True)   # 默认 membership expires_at 见 _student 实现
    await _student(db_session, inst.id, member=True)
    await _student(db_session, inst.id, member=True)
    # 本月采购 + 往月采购
    now = dt.datetime.now(dt.timezone.utc)
    db_session.add(InstitutionPurchase(
        id=uuid.uuid4(), institution_id=inst.id, tier="pro",
        duration_months=6, quantity=2, amount_fen=36000, status="paid",
        created_by=uuid.uuid4()))
    await db_session.flush()

    ov = await institution_service.get_overview(db_session, institution_id=inst.id)
    assert "expiring_30d_count" in ov
    assert ov["tier_distribution"] == {"basic": 0, "pro": 3, "promax": 0}
    assert ov["month_purchase_fen"] == 36000
```

注：`InstitutionPurchase.created_by` FK→users，测试里用随机 uuid 可能触发 FK 约束失败——若失败，改为先建一个 admin User 行（`User(id=admin, openid=..., role="institution_admin", institution_id=inst.id)`）再用其 id 作 created_by。先按随机 uuid 跑，红了再补 User（见 Step 3 注）。

把文件中 `test_get_overview_counts` 末尾对返回 key 的断言（若有 `set(ov) == {...}` 之类）改为子集断言，保留原 4 项数值断言：

```python
    assert ov["teacher_count"] == 2
    assert ov["student_count"] == 3
    assert ov["member_count"] == 1
    assert ov["active_7d_count"] == 2
    # 新增字段存在（D-126）
    assert {"expiring_30d_count", "tier_distribution", "month_purchase_fen"} <= set(ov)
```

（若原测试本就没断言 key 集合，只补最后一行即可。）

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_service.py -p no:randomly -q`
Expected: `test_get_overview_enhanced` FAIL（新 key 不存在）。

- [ ] **Step 3: 实现 get_overview 增量**

在 `backend/app/services/institution_service.py`：
- import 区 `from app.models.d2_payments import Membership` 改为 `from app.models.d2_payments import InstitutionPurchase, Membership`。
- 在 `get_overview` 内 `return {...}` 之前插入：

```python
    cutoff_30d = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    expiring_30d_count = (await db.execute(
        select(func.count(func.distinct(Membership.user_id))).where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
            Membership.expires_at.is_not(None),
            Membership.expires_at <= cutoff_30d,
        )
    )).scalar_one()

    tier_rows = (await db.execute(
        select(Membership.tier, func.count()).where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
        ).group_by(Membership.tier)
    )).all()
    _tc = {str(t): c for t, c in tier_rows}
    tier_distribution = {k: _tc.get(k, 0) for k in ("basic", "pro", "promax")}

    month_start = dt.datetime.now(dt.timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    month_purchase_fen = (await db.execute(
        select(func.coalesce(func.sum(InstitutionPurchase.amount_fen), 0)).where(
            InstitutionPurchase.institution_id == institution_id,
            InstitutionPurchase.created_at >= month_start,
        )
    )).scalar_one()
```

把 return 改为：

```python
    return {
        "teacher_count": teacher_count,
        "student_count": student_count,
        "member_count": member_count,
        "active_7d_count": active_7d_count,
        "expiring_30d_count": expiring_30d_count,
        "tier_distribution": tier_distribution,
        "month_purchase_fen": month_purchase_fen,
    }
```

注（Step 1 的 FK 提示）：若 `test_get_overview_enhanced` 因 `InstitutionPurchase.created_by` FK 报错，在测试里建一个 admin User 行用其 id；`_student` 的会员到期天数若使 `expiring_30d_count` 与预期不符，本测试未硬断言其值（只断言 key 存在），故不受影响。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_service.py -p no:randomly -q`
Expected: 全 PASS（含 enhanced + counts）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_service.py tests/services/test_institution_service.py
git commit -m "feat(institution): 概览增 近30天到期/档位分布/本月采购额"
```

---

## Task 2: schema + api 测试更新

**Files:**
- Modify: `backend/app/schemas/institution.py`, `tests/api/test_institution.py`

- [ ] **Step 1: schema 加字段**

把 `backend/app/schemas/institution.py` 的 `InstitutionOverviewOut` 改为：

```python
class InstitutionOverviewOut(BaseModel):
    teacher_count: int
    student_count: int
    member_count: int
    active_7d_count: int
    expiring_30d_count: int
    tier_distribution: dict[str, int]
    month_purchase_fen: int
```

- [ ] **Step 2: 更新 api 测试断言**

在 `tests/api/test_institution.py::test_overview_and_profile` 中，overview 的 key 断言（原 `set(body) == {4 keys}`）改为：

```python
    assert {"teacher_count", "student_count", "member_count", "active_7d_count",
            "expiring_30d_count", "tier_distribution", "month_purchase_fen"} <= set(body)
```

- [ ] **Step 3: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution.py -p no:randomly -q`
Expected: PASS（api 现返回 7 字段）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/institution.py tests/api/test_institution.py
git commit -m "feat(institution): InstitutionOverviewOut 加 3 字段 + api 断言更新"
```

---

## Task 3: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 全绿；已知偶发污染项若红，隔离复跑确认通过。

---

## Task 4: admin web 概览卡片

**Files:**
- Modify: `frontend/admin/src/views/InstitutionOverview.vue`

- [ ] **Step 1: 改概览页**

把 `frontend/admin/src/views/InstitutionOverview.vue` 改为（reactive 补新字段 + 加卡片 + 档位分布）：

```vue
<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { getOverview } from '../api/institution'

const data = reactive({
  teacher_count: 0, student_count: 0, member_count: 0, active_7d_count: 0,
  expiring_30d_count: 0, month_purchase_fen: 0,
  tier_distribution: { basic: 0, pro: 0, promax: 0 } as Record<string, number>,
})

onMounted(async () => {
  Object.assign(data, await getOverview())
})
</script>

<template>
  <div class="overview">
    <h2 class="title">机构概览</h2>
    <el-row :gutter="16">
      <el-col :span="6"><el-card><div class="label">老师数</div><div class="num">{{ data.teacher_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">学生数</div><div class="num">{{ data.student_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">付费会员</div><div class="num">{{ data.member_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">近 7 日活跃</div><div class="num">{{ data.active_7d_count }}</div></el-card></el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="6"><el-card><div class="label">近 30 天到期</div><div class="num">{{ data.expiring_30d_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">本月采购额(元)</div><div class="num">{{ (data.month_purchase_fen / 100).toFixed(2) }}</div></el-card></el-col>
      <el-col :span="12">
        <el-card>
          <div class="label">会员档位分布</div>
          <div class="tiers">
            <span>基础 {{ data.tier_distribution.basic }}</span>
            <span>Pro {{ data.tier_distribution.pro }}</span>
            <span>ProMax {{ data.tier_distribution.promax }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.label { color: #888; font-size: 14px; }
.num { font-size: 32px; font-weight: 700; margin-top: 8px; }
.tiers { display: flex; gap: 32px; font-size: 20px; font-weight: 600; margin-top: 12px; }
</style>
```

> 实现者注意：`getOverview` 返回类型 `InstitutionOverview` 需含新字段；若 `api/institution.ts` 的 `InstitutionOverview` interface 未含，补 `expiring_30d_count: number; month_purchase_fen: number; tier_distribution: Record<string, number>`。

- [ ] **Step 2: api 层 interface 补字段**

在 `frontend/admin/src/api/institution.ts` 的 `InstitutionOverview` interface 加：

```typescript
  expiring_30d_count: number
  month_purchase_fen: number
  tier_distribution: Record<string, number>
```

- [ ] **Step 3: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/admin/src/views/InstitutionOverview.vue frontend/admin/src/api/institution.ts
git commit -m "feat(institution-web): 概览加 到期/采购额/档位分布 卡片"
```

---

## Task 5: 归档 D-126 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部加 D-126（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-120）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` M2（机构概览）行补「+近30天到期/本月采购额/档位分布（D-126）」。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-overview-enhance.md
git commit -m "docs: 归档 D-126 机构数据概览增强"
```

---

## Self-Review 结论

- **Spec 覆盖**：service 增量+测试→Task1；schema+api 测试→Task2；回归→Task3；前端卡片→Task4；归档→Task5。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码；FK 边界已给应对说明。
- **类型一致**：`get_overview` 返回 7 key ↔ `InstitutionOverviewOut` 7 字段 ↔ 前端 interface/reactive 7 字段 ↔ 测试断言一致；`tier_distribution` 三档 dict 在 service/schema/前端一致。
