# 机构端切片五：批量续费（3b，D-124）设计文档

> 机构端 MVP 第五切片。零迁移、dev-mock 即付无花钱。

## 目标

机构管理员在 admin web 列出名下有有效会员的学生（可按「近 N 天到期」筛选），勾选后批量续费指定月数（dev-mock 即时已支付），各学生会员到期日相应延长。

## 背景与现状

- `membership_service.activate_membership(db, *, order)` 的 **renew 分支**：当 `order.order_type == "renew"` 且 `existing.tier == order.tier` 时，从 `max(existing.expires_at, now)` 延长 `order.duration_months`。可直接复用。
- `Order` 模型可造 renew 单（payer/beneficiary/order_type/tier/duration_months/amount_fen/status/order_no 必填）。
- `institution_purchase_service._TIER_MONTHLY_FEN`（basic1500/pro3000/promax5000 分/月）可算金额。
- `memberships` 有 `is_active` 部分唯一索引（每用户至多一条 active）。
- 机构体系 D-120~123 就绪；`students.institution_id` 标识机构学生。

## 架构

机构管理员后台「批量续费」页 → 列出名下有 active 会员的学生（档位/到期日，可按近 N 天到期筛）→ 勾选 + 选续费月数 → dev-mock 即付 → 对每个选中学生造一张已支付 renew Order（档位=该生现有会员档位，时长=所选月数）→ `activate_membership` 从 `max(到期,now)` 延长。零迁移、无真实扣款。

## 后端组件

### `institution_renew_service.py`（新建）

```
list_renewable_students(db, *, institution_id, expiring_days: int | None = None)
    -> list[tuple[uuid.UUID, str | None, str, datetime]]
    # 返回 (student_user_id, nickname, tier, expires_at)
    # 范围：students.institution_id == institution_id 且 该生有 memberships.is_active=True 的记录
    # expiring_days 非空 → 仅保留 expires_at <= now + expiring_days 天（含已过期 expires_at<=now）
    # 按 expires_at 升序

batch_renew(db, *, institution_id, student_ids: list[uuid.UUID], duration_months: int, operator_id)
    -> dict   # {"renewed_count": int, "total_amount_fen": int, "skipped": list[str]}
    # 逐个 student_id：
    #   - 校验该生 students.institution_id == institution_id 且有 active 会员，否则计入 skipped（不抛错）
    #   - tier = 该生 active membership.tier
    #   - 造 Order(order_no 合成, payer_id=operator_id, beneficiary_id=student,
    #       order_type="renew", tier=tier, duration_months=duration_months,
    #       amount_fen=_TIER_MONTHLY_FEN[tier]*duration_months, status="paid")，flush
    #   - await membership_service.activate_membership(db, order=order)  # renew 分支延长
    #   - renewed_count += 1; total_amount_fen += amount_fen
```

金额单价复用 `institution_purchase_service._TIER_MONTHLY_FEN`（import 引用，避免重复定义）。

### API（`InstAdminDep = require_role("institution_admin")`，机构来自 `current_user.institution_id`）

- `GET /institution/renewable-students?expiring_days=` → `list[RenewableStudentOut]`
- `POST /institution/batch-renew`（body `BatchRenewRequest`）→ `BatchRenewResult`

### schemas（`schemas/institution.py` 追加）

- `RenewableStudentOut`：student_id: uuid / nickname: str|None / tier: str / expires_at: datetime
- `BatchRenewRequest`：student_ids: list[uuid.UUID] / duration_months: int
- `BatchRenewResult`：renewed_count: int / total_amount_fen: int / skipped: list[uuid.UUID]

## 前端（admin web）

- `views/InstitutionRenew.vue`（institution_admin 菜单加「批量续费」）：
  - 「仅看近 30 天到期」开关（切换 expiring_days=30/空）+ 刷新
  - 学生表格：勾选框 / 昵称 / 档位 / 到期日
  - 续费月数 `el-input-number` + 「批量续费（dev-mock 即付）」按钮（无勾选时禁用）
  - 提交后 toast：成功 N 人、跳过 M 人、合计金额；刷新列表
- `api/institution.ts`：`listRenewableStudents(expiringDays?) / batchRenew(studentIds, durationMonths)`。
- router + 菜单项。

## 测试

**service**：
- `list_renewable_students`：含 active 会员学生入列；无会员学生不入列；`expiring_days` 筛掉到期较远的。
- `batch_renew`：选中学生会员 `expires_at` 延长 duration_months；金额累计正确。
- `batch_renew` 跳过无 active 会员 / 不属本机构的 student_id（计入 skipped，不抛错）。
- 跨机构隔离：A 机构 batch_renew 传 B 机构学生 → 计入 skipped。

**api**：
- 机构管理员 列表 → 批量续费 → 该生会员到期延后（GET 列表 expires_at 变大）全链路。
- platform_admin 访问 `/institution/renewable-students` → 403（沿用鉴权）。

**dev-mock**：纯 DB，无真实支付/LLM/媒体。

## 不做（后续切片）

账单导出/发票（3c）、分成收益（3d）、续费时改档位/升级、prod 真实定价与微信支付对接、续费失败重试队列、续费通知聚合。

## 影响范围

- 新增：`institution_renew_service.py`、admin web `views/InstitutionRenew.vue`。
- 修改：`schemas/institution.py`、`api/v1/institution.py`；admin web `api/institution.ts`、router、MainLayout 菜单。
- 无数据库迁移，无新依赖，无付费调用。
