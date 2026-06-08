# V2 M26 — 机构批量续费迁移至 V2 学期模型

## 背景
`institution_renew_service.batch_renew` 和 `institution/batch-renew` 端点
仍使用 V1 `Membership` 模型（`is_active`, `expires_at`, `tier`）和 `duration_months`。
V2 架构使用 `purchased_semesters` 表（textbook_version, grade, semester, tier, expires_at）。

批量续费页面 `InstitutionRenew.vue` 也使用 `months` 参数（V1）。

## 目标
1. `list_renewable_students` 改查 `purchased_semesters`（取最近到期的记录）
2. `batch_renew` 改为创建新 `purchased_semesters` 记录（expires_at 顺延 6 个月 × semesters）
3. 后端请求体改 `semesters: int`（学期数）替代 `duration_months`
4. Institution frontend `InstitutionRenew.vue` 改为「续费 N 学期」（1学期=6个月）

## 验收标准
- 续费后学生对应 `purchased_semesters` 记录的 `expires_at` 顺延 N * 6 个月
- `列表` 仍显示即将到期的学生（按 expires_at 最近的学期过滤）
- 向后兼容：旧 V1 `Membership` 数据在机构后台不可见（隔离，不干扰）
