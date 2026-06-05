# D-129：独立机构前端应用（机构后台与平台后台物理拆分）设计文档

> 零迁移、无花钱。新建独立前端 + 后端登录拆分 + admin web 收回机构页面。

## 目标

把机构管理员后台从 admin web 拆出为独立 Vue 应用 `frontend/institution`，独立登录入口；后端拆登录端点（平台/机构各自的门，错角色直接 401）；admin web 移除所有机构管理员页面/菜单/路由，登录只放 platform_admin。

## 背景与现状

- 当前 admin web（`frontend/admin`）一份产物同时承载 platform_admin 与 institution_admin，按 JWT role 在 `router/index.ts` beforeEach + `MainLayout.vue` 菜单 `v-if` 分流。
- `/admin/auth/login`（D-120）当前放行 platform_admin + institution_admin 两种角色（`admin_auth_service.authenticate` 内 `role in (platform_admin, institution_admin)`）。
- 后端业务端点已各自 `require_role(...)` + 机构隔离，无数据越权；本切片只解决「同一前端产物 + 同一登录门」的耦合面。
- admin web 现有机构相关文件：视图 `InstitutionOverview/Profile/Teachers/Purchases/Renew/Bills.vue`（6，institution_admin 用）、`Institutions.vue`（机构审核，**platform_admin 用，保留**）、`Notifications.vue`（通用）；api `institution.ts`（机构）、`admin.ts`（含机构审核接口，保留）、`notifications.ts`。
- 脚手架：Vue3 + Vite + Element Plus + pinia + vue-router + unplugin-auto-import/components；`vite.config.ts` proxy `/api → 127.0.0.1:8000`；`request.ts` baseURL `/api/v1`。

## 后端组件（纵深防御，零迁移）

### `admin_auth_service.authenticate`（改签名）

```python
async def authenticate(db, *, username, password,
                       allowed_roles: tuple[str, ...] = ("platform_admin",)) -> User | None:
    ...
    if str(user.role) not in allowed_roles:
        return None
    ...
```

- `/admin/auth/login`（admin.py）调用不传 allowed_roles → 默认仅 platform_admin（撤销 D-120 双角色放行）。

### 新增 `POST /institution/auth/login`（institution.py，无鉴权依赖）

```python
@router.post("/auth/login", response_model=BaseResponse[TokenResponse])
async def institution_login(body: AdminLoginRequest, db: DbDep):
    user = await admin_auth_service.authenticate(
        db, username=body.username, password=body.password,
        allowed_roles=("institution_admin",))
    if user is None:
        raise AppError(code=401, message="用户名或密码错误")
    return make_ok(TokenResponse(
        access_token=create_access_token(str(user.id), str(user.role)),
        refresh_token=create_refresh_token(str(user.id))))
```

需 import `AdminLoginRequest`/`TokenResponse`（app.schemas.auth）、`create_access_token`/`create_refresh_token`（app.core.security）、`admin_auth_service`。放在 `/institution` 路由内（已注册，prefix=/institution）。

## 新建 `frontend/institution`（dev 端口 5175）

照搬 admin 脚手架，差异化内容：

- `package.json`：name=`institution`，scripts/deps 同 admin。
- `vite.config.ts`：同 admin（proxy `/api → 127.0.0.1:8000`），`server.port = 5175`。
- `index.html` / `tsconfig*.json` / `main.ts`（含 ElementPlus、pinia、router 注册）/ `App.vue`：照搬。
- `src/api/request.ts`：照搬（baseURL `/api/v1`，401 跳 `#/login`，token 存 `institution_token`）。
- `src/api/institution.ts`：从 admin web 原样搬（getOverview/profile/teachers/purchases/renew/bills 全套）。
- `src/api/notifications.ts`：照搬。
- `src/stores/auth.ts`：`login(username,password)` → `POST /institution/auth/login`；token 存 `institution_token`；无 role 分支（单角色）。
- `src/views/`：`Login.vue`（标题「机构管理后台」，调 store.login）、`InstitutionOverview/Profile/Teachers/Purchases/Renew/Bills.vue`、`Notifications.vue`（从 admin web 迁移，import 路径不变）。
- `src/layouts/MainLayout.vue`：固定机构菜单（概览/资料/老师管理/学生采购/批量续费/账单/通知），无 role 判断；退出登录。
- `src/router/index.ts`：登录守卫（未登录→/login），子路由为机构 7 页 + 默认重定向 `/overview`；无 role 分流。

## admin web 收回

- 删除：`views/InstitutionOverview.vue`、`InstitutionProfile.vue`、`InstitutionTeachers.vue`、`InstitutionPurchases.vue`、`InstitutionRenew.vue`、`InstitutionBills.vue`、`api/institution.ts`。
- 保留：`Institutions.vue`（机构审核）、`Notifications.vue`、`admin.ts`（机构审核接口在此）。
- `router/index.ts`：删 `institution/*` 路由；去掉 beforeEach 里的 role 分流块（恢复纯登录态守卫）。
- `layouts/MainLayout.vue`：删除 `institution_admin` 菜单分支（`v-if`/`v-else` 结构），恢复纯 platform 菜单（数据大盘/仿真题审核/知识点内容/定价配置/作文模板/机构审核/通知）。
- `stores/auth.ts`：移除 role 解码（不再用于菜单）或保留无害；本设计选择**移除** decodeRole 简化（菜单不再依赖 role）。

## 测试

**后端**（`tests/api/`）：
- `/institution/auth/login`：机构账号 200 + 返回 token；平台账号 401；错密码 401。
- `/admin/auth/login`：平台账号 200；机构账号 401（撤销双放行）。
- **连带修改（重要）**：以下测试的「机构管理员登录」helper 当前走 `/admin/auth/login`，须改为 `/institution/auth/login`，否则收紧后全失败：`tests/api/test_institution_teacher.py`、`test_institution_purchase.py`、`test_institution_renew.py`、`test_institution_billing.py`、`test_teacher_quota.py`（这些文件的 `_login`/`_admin_login`）。`test_admin_institution.py`（platform_admin）与 `test_institution.py`（D-120 机构管理员登录）也需核对：凡 institution_admin 登录一律改 `/institution/auth/login`，platform_admin 保持 `/admin/auth/login`。
- 后端全量回归绿。

**前端**：`frontend/institution` 与 `frontend/admin` 各自 `npm run build` 通过。

**dev-mock**：纯逻辑，无付费/LLM/媒体。

## 不做（后续）

独立域名 + nginx 部署分流（dev 用 5174/5175 不同端口；上线清单记一条「institution 前端单独部署」）、SSO、机构端忘记密码、机构端未读红点。

## 影响范围

- 后端：`admin_auth_service.py`（authenticate 加 allowed_roles）、`api/v1/institution.py`（+登录端点）、`api/v1/admin.py`（登录默认 platform_admin，无需改调用即默认收紧）。
- 新增：`frontend/institution/**`（整套）。
- 修改/删除：`frontend/admin` 6 视图 + institution.ts 删除、router/MainLayout/auth.ts 收回。
- 测试：新增 `tests/api/test_institution_login.py`；调整既有受影响的 admin 登录测试。
- 无数据库迁移、无新依赖、无付费调用。
