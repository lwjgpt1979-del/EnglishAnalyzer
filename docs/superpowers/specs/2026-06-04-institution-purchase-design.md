# 机构端切片三：学生账号采购与分配（闭环 3a，D-122）设计文档

> 机构端 MVP 第三切片。迁移 0020；dev-mock 支付，无真实花钱。

## 目标

机构管理员在 admin web 按 档位 + 时长(月) + 数量 批量采购学生会员（dev-mock 即时已支付），系统生成 N 个激活码；学生在小程序输激活码，获得对应会员并归属该机构。

## 背景与现状

- `Order` 是个人单（payer/beneficiary 单用户 + duration_months/tier/amount_fen/status），不适配批量席位 → 需新表。
- `membership_service.activate_membership(db, *, order)` 走 V1 路径（order_type=new、tier、duration_months）创建 Membership，可复用。
- 微信支付已 dev-mock；institution/teachers/students 体系（D-120/121）就绪。
- 现仅 `SemesterPricing`（按学期 yuan），无「按月」单价表。

## 架构

机构管理员后台下单 → dev-mock 即时 `status=paid` → 生成 N 个激活码 → 学生小程序输码激活 → 造一张「已支付」合成 `Order`（order_type=new、tier、duration_months、beneficiary=学生）调 `activate_membership` 发 V1 会员 + 设 `students.institution_id`。新表 `institution_purchases` + `activation_codes`，迁移 0020。dev-mock 全程无真实支付。

## 数据模型（迁移 0020）

### `institution_purchases`
- id (UUID PK)
- institution_id (FK→institutions, NOT NULL)
- tier (membership_tier_enum 复用，限 basic/pro/promax)
- duration_months (int, NOT NULL)
- quantity (int, NOT NULL)
- amount_fen (int, NOT NULL)
- status (str, NOT NULL, dev-mock 固定 "paid")
- created_by (FK→users, NOT NULL，管理员)
- created_at (timestamptz, server_default now)

### `activation_codes`
- id (UUID PK)
- code (str(12), unique, NOT NULL)
- purchase_id (FK→institution_purchases, NOT NULL)
- tier (membership_tier_enum)
- duration_months (int, NOT NULL)
- status (str, NOT NULL, "unused"/"used"，默认 unused)
- used_by (FK→users, nullable)
- used_at (timestamptz, nullable)
- created_at (timestamptz, server_default now)

模型加入 `d2_payments.py`；`models/__init__.py` 同步导出。

> **定价**：无「按月」单价表，本切片在 service 内用 dev 占位月单价（per-tier：basic=1500 分、pro=3000 分、promax=5000 分/月）算 `amount_fen = unit × duration_months × quantity`。prod 真实定价后续接（记入"未做"）。

## 后端组件

### `institution_purchase_service.py`（新建）

```
_TIER_MONTHLY_FEN = {"basic": 1500, "pro": 3000, "promax": 5000}

create_purchase(db, *, institution_id, created_by, tier, duration_months, quantity)
    -> tuple[InstitutionPurchase, list[ActivationCode]]
    # amount_fen = _TIER_MONTHLY_FEN[tier] * duration_months * quantity
    # 建 purchase(status="paid")；生成 quantity 个 12 位唯一 code（查重）
list_purchases(db, *, institution_id) -> list[tuple[InstitutionPurchase, int used, int total]]
    # 每单返回 已用码数 / 总码数
get_purchase_codes(db, *, institution_id, purchase_id) -> list[ActivationCode]
    # 校验 purchase.institution_id == institution_id，否则 AppError(404)
```

### `activation_service.py`（新建）

```
activate_code(db, *, student_user_id, code) -> Membership | None
    # 校验 code：status=unused，否则 AppError(400)
    # 学生已是机构生（students.institution_id 非空）→ AppError(409)
    # 造合成 Order(order_no 合成, payer_id=code.purchase.created_by,
    #   beneficiary_id=student, order_type="new", tier, duration_months,
    #   amount_fen=0, status="paid")，db.add
    # membership = await membership_service.activate_membership(db, order=order)
    # 设 students.institution_id = code.purchase.institution_id
    # code.status="used"; code.used_by=student; code.used_at=now
    # return membership
```

### API

机构管理员（`InstAdminDep`，机构来自 `current_user.institution_id`）：
- `POST /institution/purchases`（body: tier/duration_months/quantity）→ `PurchaseOut`（含 codes）
- `GET /institution/purchases` → `list[PurchaseListItem]`（含 used/total）
- `GET /institution/purchases/{purchase_id}/codes` → `list[ActivationCodeOut]`

学生（`require_role("student")`）：
- `POST /memberships/activate-code`（body: code）→ `BaseResponse[dict]`（tier/expires_at 摘要）

### schemas（`schemas/institution.py` 追加）

- `PurchaseCreateRequest`：tier: str / duration_months: int / quantity: int
- `ActivationCodeOut`：code / status / used_at: datetime|None
- `PurchaseOut`：id / tier / duration_months / quantity / amount_fen / status / created_at / codes: list[ActivationCodeOut]
- `PurchaseListItem`：id / tier / duration_months / quantity / amount_fen / status / created_at / used_count / total_count
- `ActivateCodeRequest`：code: str

## 前端

### admin web
- `views/InstitutionPurchases.vue`：下单表单（档位下拉 / 时长月数 / 数量 → 前端按相同单价预估金额展示）、提交后弹出激活码列表；采购记录表（档位/时长/数量/金额/已用/总数），点行展开看码（可复制）。
- `api/institution.ts`：`createPurchase / listPurchases / getPurchaseCodes`。
- router + 菜单第四项「学生采购」。

### 小程序学生端
- `pages/membership/activate.vue`：输激活码 → 调激活 → 成功 toast。
- `api/membership.ts`：`activateCode(code)`。
- 会员页/个人中心加「激活码」入口。

## 测试

**service**：
- `create_purchase`：生成 quantity 个码、amount_fen 正确、status=paid。
- `activate_code`：发 Membership（查得 active）、设 students.institution_id、码置 used；重复用码 → 400；已是机构生 → 409。
- `get_purchase_codes` 跨机构 → 404。

**api**：
- 管理员下单 → 看码 → 学生激活 → 学生会员 active 全链路。
- 学生用已用码 → 400。
- platform_admin 访问 `/institution/purchases` → 403（沿用鉴权）。

**dev-mock**：无真实支付/LLM/媒体调用。

## 不做（后续切片）

批量续费（3b）、账单导出/发票（3c）、分成收益（3d）、激活时分配老师、prod 真实定价与微信支付对接、采购退款。

## 影响范围

- 新增：迁移 0020、`institution_purchase_service.py`、`activation_service.py`、admin web `InstitutionPurchases.vue`、小程序 `pages/membership/activate.vue`。
- 修改：`d2_payments.py`（2 新表）、`models/__init__.py`、`schemas/institution.py`、`api/v1/institution.py`、`api/v1/memberships.py`；admin web `api/institution.ts`/router/MainLayout；小程序 `api/membership.ts`/入口/`pages.json`。
- 一个迁移 0020（2 张新表），无新依赖，无真实付费调用。
