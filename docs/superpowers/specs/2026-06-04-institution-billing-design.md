# 机构端切片六：机构账单导出（3c，D-125）设计文档

> 机构端 MVP 第六切片。零迁移、CSV 前端生成、无花钱。

## 目标

机构管理员在 admin web「账单」页查看本机构的采购单与续费单合并账单（按时间倒序），并一键导出 CSV。

## 背景与现状

- `institution_purchases`（D-122）：`institution_id / tier / duration_months / quantity / amount_fen / status / created_at`。
- `orders`（续费单，D-124 batch_renew 生成）：`order_type='renew'`、`payer_id=机构管理员(operator)`、`tier / duration_months / amount_fen / created_at`，**无 institution_id**，经 `payer_id → users.institution_id` 关联机构。
- 机构体系 D-120~124 就绪；`InstAdminDep = require_role("institution_admin")`。

## 架构

机构管理员后台「账单」页 → 后端把该机构的采购单（`institution_purchases`）与续费单（`orders.order_type='renew'` 且付款人属本机构）合并成统一账单条目，按时间倒序返回 → 前端表格展示 + 「导出 CSV」客户端 Blob 下载。零迁移、无付费调用。

## 后端组件

### `institution_billing_service.py`（新建）

```
list_bills(db, *, institution_id) -> list[dict]
    # 每条：{"date": datetime, "type": str, "summary": str, "amount_fen": int}
    # 采购：select InstitutionPurchase where institution_id == institution_id
    #   type="采购"，summary=f"{tier} × {quantity}（{duration_months}月）"
    # 续费：select Order where order_type=="renew"
    #         and payer_id in (select User.id where User.institution_id == institution_id)
    #   type="续费"，summary=f"{tier} 续费 {duration_months}月"
    # 合并，按 date 倒序
```

### API（`InstAdminDep`，机构来自 `current_user.institution_id`）

- `GET /institution/bills` → `BaseResponse[list[BillItemOut]]`

### schemas（`schemas/institution.py` 追加）

- `BillItemOut`：date: datetime / type: str / summary: str / amount_fen: int

## 前端（admin web）

- `views/InstitutionBills.vue`（institution_admin 菜单加「账单」）：
  - 表格：日期 / 类型（采购·续费）/ 明细 / 金额（元，amount_fen/100）
  - 顶部合计金额展示（sum amount_fen / 100）
  - 「导出 CSV」按钮：前端把当前列表拼成 CSV 文本（表头 `日期,类型,明细,金额(元)`），用 Blob + a[download] 触发下载（文件名 `机构账单_YYYYMMDD.csv`，加 UTF-8 BOM 防 Excel 中文乱码）
- `api/institution.ts`：`listBills()`。
- router + 菜单项。

## 测试

**service**：
- `list_bills` 含采购条目（type=采购）+ 续费条目（type=续费），按 date 倒序。
- 跨机构隔离：A 机构 bills 不含 B 机构的采购，也不含 B 机构管理员付款的续费单。

**api**：
- 机构管理员 GET /institution/bills → 含采购 + 续费两类条目。
- platform_admin 访问 → 403（沿用鉴权）。

**dev-mock**：纯 DB，无付费/LLM/媒体。CSV 生成为前端纯函数，不单测。

## 不做（后续切片）

发票真实开具、分成收益（3d）、按时间段/类型筛选、分页、导出 Excel、退款条目。

## 影响范围

- 新增：`institution_billing_service.py`、admin web `views/InstitutionBills.vue`。
- 修改：`schemas/institution.py`、`api/v1/institution.py`；admin web `api/institution.ts`、router、MainLayout 菜单。
- 无数据库迁移，无新依赖，无付费调用。
