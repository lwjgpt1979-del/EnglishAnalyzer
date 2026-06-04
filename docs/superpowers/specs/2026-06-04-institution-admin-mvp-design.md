# 机构后台基础壳 + 数据概览（D-120）设计文档

> 机构端 MVP 第一切片。零迁移、dev-mock 无花钱。

## 目标

为机构管理员（`role=institution_admin`）提供后台入口：用同一 admin web 登录，看到「机构概览」和「机构资料」两个页面。机构概览展示名下老师数、学生数、付费会员数、近 7 日活跃学生数；机构资料可查看并编辑机构已有字段（名称/联系电话/地址）。

## 背景与现状

- `institutions` 表已存在，字段：`id / name / contact_phone / commission_rate / province_code / city_code / address / status(pending|active|suspended) / created_at / updated_at`。**无 logo、无 intro 列**。
- `user_role` 枚举已含 `institution_admin / branch_admin / platform_admin`。
- `users` 等模型已有 `institution_id` 外键关联。
- 机构 service / api / 前端目前**全空**。
- admin web（`frontend/admin`，Vue3 + Element Plus）已存在，平台管理员用账密登录 `/admin/auth/login`，`admin_auth_service.authenticate` 当前**硬限 `platform_admin`**。

## 架构

复用 `frontend/admin`。机构管理员用同一登录页账密登录；前端解码 JWT 取 `role` 字段决定菜单：

- `institution_admin`：仅见「机构概览 / 机构资料」
- `platform_admin`：见现有全部菜单（不受影响）

后端新增 `/institution/*` 路由，`require_role("institution_admin")` 鉴权，所有查询以 `current_user.institution_id` 强隔离——机构只能看自己的数据。

## 后端组件

### 1. `admin_auth_service`（修改）

- `authenticate(db, username, password)`：放行 role ∈ `{platform_admin, institution_admin}`（platform_admin 原行为不变，纯增量）。
- 新增 `create_institution_admin(db, *, username, password, institution_id)`：创建 `role=institution_admin`、`openid="inst:{username}"`、`institution_id` 已设的 User；username 已存在则重置密码 + 角色 + 机构。供测试 / 种子使用。

### 2. `institution_service.py`（新建）

```
get_profile(db, *, institution_id) -> Institution
update_profile(db, *, institution_id, name=None, contact_phone=None, address=None) -> Institution
get_overview(db, *, institution_id) -> dict
    # {"teacher_count", "student_count", "member_count", "active_7d_count"}
```

**概览口径**（全部复用现有表）：

| 指标 | 口径 |
|------|------|
| teacher_count | `users` 中 `institution_id=X 且 role='teacher'` 计数 |
| student_count | `users` 中 `institution_id=X 且 role='student'` 计数 |
| member_count | 名下学生中存在 `memberships.is_active=True 且 tier≠'free'` 的人数 |
| active_7d_count | 名下学生中近 7 日有打卡（check-in）或错题上传（wrong_questions.created_at）记录的人数 |

`update_profile` 仅允许编辑 `name / contact_phone / address`（均为已有列），不触碰 `status / commission_rate / 省市编码`。

### 3. `api/v1/institution.py`（新建，prefix `/institution`）

- `GET /profile` → `InstitutionProfileOut`
- `PATCH /profile`（body `InstitutionProfileUpdate`）→ `InstitutionProfileOut`
- `GET /overview` → `InstitutionOverviewOut`
- 登录复用 `/admin/auth/login`（已有）。
- `InstitutionAdminDep = Annotated[User, Depends(require_role("institution_admin"))]`。
- 注册进 `main.py`。

### 4. `schemas/institution.py`（新建）

- `InstitutionProfileOut`：id / name / contact_phone / province_code / city_code / address / status / created_at
- `InstitutionProfileUpdate`：name? / contact_phone? / address?（均可选）
- `InstitutionOverviewOut`：teacher_count / student_count / member_count / active_7d_count

## 前端（admin web）

- `stores/auth.ts`：登录成功后解码 JWT payload 取 `role`（`sub` 为 user id，`role` 为角色），存入 store；持久化以便刷新后菜单正确。
- `MainLayout`（或菜单组件）：按 `role` 条件渲染菜单项。机构管理员仅见「机构概览 / 机构资料」。
- `views/InstitutionOverview.vue`：4 张数据卡（老师 / 学生 / 会员 / 近 7 日活跃）。
- `views/InstitutionProfile.vue`：资料查看 + 编辑表单（name / contact_phone / address 可编辑；省市编码、状态只读）。
- `api/institution.ts`：`getOverview / getProfile / updateProfile`。
- router：加 `/institution/overview`、`/institution/profile` 两条路由 + role 守卫（institution_admin 默认进 overview）。

## 测试

**service 层**：

- `get_overview` 计数正确：构造 1 机构 + N 老师 + M 学生 + 部分付费会员 + 部分近 7 日活跃，断言四个计数。
- **跨机构隔离**：构造 A、B 两机构，断言 A 的 overview 不含 B 的成员。
- `update_profile` 改 name/contact_phone/address 生效。

**api 层**：

- 机构管理员登录（`create_institution_admin` 种子）→ `/institution/overview`、`/institution/profile` 200。
- `platform_admin` 访问 `/institution/*` → 403。
- A 机构管理员看不到 B 机构数据。

**dev-mock**：无 LLM / 媒体 / 支付调用，纯 DB，无花钱。

## 不做（后续切片）

- logo / 机构简介（需新增列 → 迁移，留待后续）
- 名下老师账号管理（邀请 / 停用）
- 学生账号批量采购与分配
- 套餐额度配置
- 企业微信通知
- 入驻审核（超管侧）

## 影响范围

- 新增：`institution_service.py`、`api/v1/institution.py`、`schemas/institution.py`、admin web 两个 view + api + router/menu 改动。
- 修改：`admin_auth_service.authenticate`（放行 institution_admin）、`main.py`（注册路由）、`stores/auth.ts`、`MainLayout`。
- 无数据库迁移，无新依赖，无付费调用。
