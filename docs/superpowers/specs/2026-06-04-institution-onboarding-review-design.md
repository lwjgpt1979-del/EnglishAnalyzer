# 机构端切片四：入驻审核（超管侧，D-123）设计文档

> 机构端 MVP 第四切片。零迁移、dev-mock 无花钱。

## 目标

平台超管（platform_admin）在 admin web 录入待审核机构、查看机构列表（按状态筛选）、审核通过（机构置 active + 自动开通机构管理员账号并一次性返回账号密码）或拒绝（机构置 suspended）。

## 背景与现状

- `institution_status` 枚举：`pending / active / suspended`（无 rejected）。`institutions.status` 默认 pending。
- 机构创建流程当前**完全不存在**（无任何入口），因此本切片自带「超管代录入 pending 机构」作为审核对象。
- `admin_auth_service.create_institution_admin(db, username, password, institution_id)`（D-120）可复用开通机构管理员账号（openid 合成、bcrypt 存 hash）。
- `AdminDep = require_role("platform_admin")`（admin.py）就绪。

## 架构

超管在 admin web 操作，端点挂 `/admin/*`（复用 AdminDep）。流程：超管代录入 pending 机构 → 审核通过（status=active + 开通机构管理员账号，返回明文账号密码供线下转交，库里仅存 hash）/ 拒绝（status=suspended）。零迁移、无付费调用。

**拒绝语义**：枚举无 rejected，拒绝置 `suspended`（兼作「未通过/冻结」）。

## 后端组件

### `admin_institution_service.py`（新建）

```
create_institution(db, *, name, contact_phone, province_code, city_code, address) -> Institution
    # status 默认 pending

list_institutions(db, *, status: str | None = None) -> list[Institution]
    # status 为空返回全部，否则按状态筛，按 created_at 倒序

approve_institution(db, *, institution_id, admin_username) -> tuple[Institution, str, str]
    # 校验机构存在且 status == "pending"，否则 AppError
    # status = "active"
    # password = 随机 10 位
    # await create_institution_admin(db, username=admin_username, password=password, institution_id=institution_id)
    # 返回 (institution, admin_username, password)  # 明文密码仅本次返回

reject_institution(db, *, institution_id) -> Institution
    # 校验存在，status = "suspended"
```

### API（`AdminDep = require_role("platform_admin")`，挂在 admin.py）

- `POST /admin/institutions`（body `AdminInstitutionCreate`）→ `AdminInstitutionOut`
- `GET /admin/institutions?status=` → `list[AdminInstitutionOut]`
- `POST /admin/institutions/{institution_id}/approve`（body `ApproveInstitutionRequest`）→ `ApproveInstitutionResult`
- `POST /admin/institutions/{institution_id}/reject` → `AdminInstitutionOut`

### schemas（`schemas/institution.py` 追加）

- `AdminInstitutionCreate`：name / contact_phone / province_code / city_code / address
- `AdminInstitutionOut`：id / name / contact_phone / province_code / city_code / address / status / created_at
- `ApproveInstitutionRequest`：admin_username: str
- `ApproveInstitutionResult`：institution_id: uuid / admin_username: str / password: str

## 前端（admin web）

- `views/Institutions.vue`（platform_admin 菜单加「机构审核」）：
  - 录入表单（名称/电话/省编码/市编码/地址）→ 建 pending
  - 状态筛选下拉（全部/pending/active/suspended）+ 列表表格
  - 每行：pending 时显示「通过」（弹窗输管理员用户名 → 调 approve → 弹出展示生成的用户名+密码，提示复制线下转交）/「拒绝」（→suspended）
- `api/admin.ts`（或现有 admin api 文件）加 4 接口；router + 菜单项（platform_admin 分支）。

## 测试

**service**：
- `create_institution` → status=pending。
- `approve_institution` → status=active + 机构管理员账号创建成功（`authenticate` 可登录）+ 返回明文密码。
- `approve_institution` 对非 pending 机构 → AppError。
- `reject_institution` → status=suspended。

**api**：
- 超管 建 → 列表（按 pending 筛到）→ 通过（返回 username+password）→ 该机构状态 active。
- 超管 拒绝 → 状态 suspended。
- 机构管理员（institution_admin）访问 `/admin/institutions` → 403（AdminDep 限 platform_admin）。

**dev-mock**：纯 DB，无 LLM/媒体/支付。

## 不做（后续切片）

补材料流程（Step 3B）、机构公开自助入驻申请端、企业微信通知、复议、机构 logo/简介、审核操作日志、approve 时用户名重复的强校验（沿用 create_institution_admin 既有「存在即重置」行为，由超管保证唯一）。

## 影响范围

- 新增：`admin_institution_service.py`、admin web `views/Institutions.vue`。
- 修改：`schemas/institution.py`、`api/v1/admin.py`（4 endpoints）；admin web api 文件 + router + MainLayout 菜单。
- 无数据库迁移，无新依赖，无付费调用。
