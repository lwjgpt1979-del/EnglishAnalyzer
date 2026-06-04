# 机构端切片七：机构数据概览增强（D-126）设计文档

> 零迁移、无花钱。扩展 D-120 概览。

## 目标

在 D-120 概览（老师数/学生数/会员数/近7日活跃）基础上，新增「近30天到期会员人数」「各档位会员分布」「本月采购金额」三项指标，并在 admin web 概览页展示。

## 背景与现状

- `institution_service.get_overview(db, *, institution_id)`（D-120）返回 `{teacher_count, student_count, member_count, active_7d_count}`。
- `InstitutionOverviewOut`（schemas/institution.py）4 字段；前端 `InstitutionOverview.vue` 4 张卡。
- 数据表：`memberships`(user_id/tier/expires_at/is_active)、`students`(id/institution_id)、`institution_purchases`(institution_id/amount_fen/created_at)。
- D-120 测试 `tests/services/test_institution_service.py::test_get_overview_counts` 断言返回 dict 恰含 4 个 key。

## 架构

扩展 `get_overview` 返回值，新增 3 项指标（均复用现有表的聚合查询）。`InstitutionOverviewOut` 加 3 字段。前端概览页加卡片。零迁移、无付费调用。

## 后端组件

### `institution_service.get_overview`（修改）

在现有 4 项基础上追加（`student_ids = select(Student.id).where(Student.institution_id == X)` 复用）：

- `expiring_30d_count`：名下学生中存在 `memberships.is_active=True 且 expires_at <= now + 30天` 的人数（含已过期 expires_at<=now）。

  ```python
  cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
  expiring_30d_count = (await db.execute(
      select(func.count(func.distinct(Membership.user_id))).where(
          Membership.user_id.in_(student_ids),
          Membership.is_active.is_(True),
          Membership.expires_at.is_not(None),
          Membership.expires_at <= cutoff,
      )
  )).scalar_one()
  ```

- `tier_distribution`：名下学生 active 会员按档位计数，固定返回三档（无则 0）。

  ```python
  rows = (await db.execute(
      select(Membership.tier, func.count()).where(
          Membership.user_id.in_(student_ids),
          Membership.is_active.is_(True),
      ).group_by(Membership.tier)
  )).all()
  counts = {str(t): c for t, c in rows}
  tier_distribution = {k: counts.get(k, 0) for k in ("basic", "pro", "promax")}
  ```

- `month_purchase_fen`：本月采购金额合计。

  ```python
  now = dt.datetime.now(dt.timezone.utc)
  month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
  month_purchase_fen = (await db.execute(
      select(func.coalesce(func.sum(InstitutionPurchase.amount_fen), 0)).where(
          InstitutionPurchase.institution_id == institution_id,
          InstitutionPurchase.created_at >= month_start,
      )
  )).scalar_one()
  ```

返回 dict 追加这 3 个 key（原 4 个不变）。需 import `InstitutionPurchase`（来自 `app.models.d2_payments`）。

### schemas（`InstitutionOverviewOut` 加字段）

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

## 前端（admin web）

`views/InstitutionOverview.vue`：
- 原 4 卡保留。
- 加 2 张卡：「近30天到期」`expiring_30d_count`、「本月采购额(元)」`month_purchase_fen/100`。
- 加一行「会员档位分布」：基础 `tier_distribution.basic` / Pro `.pro` / ProMax `.promax`。
- reactive 初始值补齐新字段，避免 undefined。

## 测试

**service**（`test_institution_service.py`）：
- 新增 `test_get_overview_enhanced`：构造名下 active 会员（含近30天到期、>30天、不同档位）+ 本月与往月采购，断言 `expiring_30d_count`、`tier_distribution`、`month_purchase_fen` 正确。
- 跨机构隔离断言（新指标不含他机构）。
- **更新** `test_get_overview_counts`：原 4 项断言保留；把「恰含 4 key」改为「包含这 4 个 key」（`>=` 子集断言），兼容新增字段。

**api**（`test_institution.py`）：`test_overview_and_profile` 的 overview key 集合断言更新为包含 7 个 key（或改为子集断言）。

**dev-mock**：纯 DB，无付费/LLM/媒体。

## 不做（后续）

日/周/月趋势图、活跃定义细化、地区分布、导出、同比环比。

## 影响范围

- 修改：`institution_service.py`（get_overview）、`schemas/institution.py`（InstitutionOverviewOut）；admin web `InstitutionOverview.vue`。
- 测试：更新 `test_get_overview_counts`、`test_overview_and_profile`，新增 `test_get_overview_enhanced`。
- 无数据库迁移，无新依赖，无付费调用。
