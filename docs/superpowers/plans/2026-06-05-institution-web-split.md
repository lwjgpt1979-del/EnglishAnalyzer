# D-129：独立机构前端应用（后台拆分）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构后台拆为独立 `frontend/institution` 应用 + 独立登录端点；admin web 收回机构页面、登录仅 platform_admin。

**Architecture:** 后端 `authenticate(allowed_roles=...)` 拆门：/admin/auth/login 仅平台、新 /institution/auth/login 仅机构。新建独立前端搬 8 页。admin web 删 6 视图+institution api、去 role 分流。零迁移、无花钱。

**Tech Stack:** FastAPI · pytest · Vue3 · Vite · Element Plus · pinia

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 前端构建：`cd frontend/admin && npm run build`、`cd frontend/institution && npm run build`。
- 本切片**无迁移、无付费调用**。

---

## Task 1: 后端登录拆分 + 连带测试修正

**Files:**
- Modify: `backend/app/services/admin_auth_service.py`, `backend/app/api/v1/institution.py`
- Test: `tests/api/test_institution_login.py`（新）+ 修正 6 个既有测试登录 helper

- [ ] **Step 1: authenticate 加 allowed_roles**

`backend/app/services/admin_auth_service.py` 的 `authenticate` 签名与判断改为：

```python
async def authenticate(
    db: AsyncSession, *, username: str, password: str,
    allowed_roles: tuple[str, ...] = ("platform_admin",),
) -> User | None:
    user = (await db.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if user is None or not user.password_hash:
        return None
    if str(user.role) not in allowed_roles:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
```

（即把原 `if str(user.role) not in ("platform_admin", "institution_admin")` 改为参数化、默认仅 platform_admin。`/admin/auth/login` 调用处不传参 → 自动收紧为仅平台。）

- [ ] **Step 2: 新增机构登录端点**

`backend/app/api/v1/institution.py`：import 区补
```python
from app.core.security import create_access_token, create_refresh_token, require_role
from app.schemas.auth import AdminLoginRequest, TokenResponse
from app.services import admin_auth_service, institution_billing_service, institution_purchase_service, institution_renew_service, institution_service
```
（`require_role` 已在；加 create_access_token/create_refresh_token、AdminLoginRequest/TokenResponse、admin_auth_service。）

在 `router` 定义之后、首个 endpoint 之前加（登录无鉴权依赖）：

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

注：`/institution` 路由整体已注册（D-120）；该端点路径为 `/api/v1/institution/auth/login`。`InstAdminDep` 等其它端点不受影响。

- [ ] **Step 3: 新登录测试**

`tests/api/test_institution_login.py`：

```python
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _mk_inst_admin(username):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst); await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()


async def _mk_platform_admin(username):
    async with _async_session_factory() as s:
        await admin_auth_service.create_admin(s, username=username, password="pw123456")
        await s.commit()


@pytest.mark.asyncio
async def test_institution_login_ok(client):
    u = f"ia_{uuid.uuid4().hex[:6]}"
    await _mk_inst_admin(u)
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_platform_cannot_login_institution_door(client):
    u = f"pa_{uuid.uuid4().hex[:6]}"
    await _mk_platform_admin(u)
    r = await client.post("/api/v1/institution/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_institution_cannot_login_admin_door(client):
    u = f"ia2_{uuid.uuid4().hex[:6]}"
    await _mk_inst_admin(u)
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": u, "password": "pw123456"})
    assert r.status_code == 401
```

- [ ] **Step 4: 修正既有测试的机构登录门**

把以下文件中「机构管理员登录」的 URL 从 `/api/v1/admin/auth/login` 改为 `/api/v1/institution/auth/login`：

- `tests/api/test_institution_purchase.py`（`_admin_login` 内，约 L34）
- `tests/api/test_institution_teacher.py`（`_admin_login` 内，约 L34）
- `tests/api/test_institution_renew.py`（`_login` 内，约 L42）
- `tests/api/test_teacher_quota.py`（`_login` 内，约 L37）

`tests/api/test_institution_billing.py`：该文件 `_login` 同时被机构测试与 platform_admin 测试用。改法：把 `_login` 改走 `/institution/auth/login`（机构用）；`test_platform_admin_forbidden` 改为内联用 `/admin/auth/login` 登录 platform_admin（不复用 `_login`）。

`tests/api/test_institution.py`：`_login`（L36）同时被 `test_overview_and_profile`(机构) 与 `test_platform_admin_forbidden`(平台) 用。改法：`_login` 走 `/institution/auth/login`；`test_platform_admin_forbidden` 内联 `/admin/auth/login` 登录其 platform_admin 账号，仍断言访问 `/institution/overview` → 403。

`tests/api/test_admin_institution.py`：`_platform_admin`（create_admin + /admin/auth/login）保持不变；`test_institution_admin_forbidden`（L73-76）机构管理员登录改 `/institution/auth/login`，仍断言 GET `/admin/institutions` → 403。

- [ ] **Step 5: 跑相关测试**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_login.py ../tests/api/test_institution.py ../tests/api/test_institution_purchase.py ../tests/api/test_institution_teacher.py ../tests/api/test_institution_renew.py ../tests/api/test_institution_billing.py ../tests/api/test_teacher_quota.py ../tests/api/test_admin_institution.py -p no:randomly -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/admin_auth_service.py backend/app/api/v1/institution.py tests/api/test_institution_login.py tests/api/test_institution*.py tests/api/test_teacher_quota.py tests/api/test_admin_institution.py
git commit -m "feat(institution): 拆登录门（/institution/auth/login 仅机构，/admin 仅平台）+ 测试修正"
```

---

## Task 2: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 全绿（已知偶发污染隔离复跑确认）。

---

## Task 3: 新建 frontend/institution 应用

**Files:** 新建 `frontend/institution/**`

- [ ] **Step 1: 复制脚手架文件（不含视图/路由/store/api）**

Run（从 admin 复制基础脚手架，再改）：

```bash
cd frontend
mkdir -p institution/src
cp admin/index.html institution/index.html
cp admin/vite.config.ts institution/vite.config.ts
cp admin/tsconfig.json admin/tsconfig.app.json admin/tsconfig.node.json institution/
cp admin/package.json institution/package.json
cp admin/.gitignore institution/.gitignore
cp admin/src/main.ts institution/src/main.ts
cp admin/src/App.vue institution/src/App.vue
cp -r admin/public institution/public
mkdir -p institution/src/api institution/src/views institution/src/layouts institution/src/router institution/src/stores
cp admin/src/api/request.ts institution/src/api/request.ts
cp admin/src/api/institution.ts institution/src/api/institution.ts
cp admin/src/api/notifications.ts institution/src/api/notifications.ts
cp admin/src/types.ts institution/src/types.ts
cp admin/src/views/InstitutionOverview.vue admin/src/views/InstitutionProfile.vue admin/src/views/InstitutionTeachers.vue admin/src/views/InstitutionPurchases.vue admin/src/views/InstitutionRenew.vue admin/src/views/InstitutionBills.vue admin/src/views/Notifications.vue institution/src/views/
```

- [ ] **Step 2: package.json 改 name**

`institution/package.json` 把 `"name": "admin"` 改为 `"name": "institution"`（其余 scripts/deps 不变）。

- [ ] **Step 3: vite.config.ts 设端口**

`institution/vite.config.ts` 的 `server` 块加/改 `port: 5175`（保留 proxy `/api → 127.0.0.1:8000`）。若原 server 块为 `{ proxy: {...} }`，改为 `{ port: 5175, proxy: {...} }`。

- [ ] **Step 4: request.ts 改 token key**

`institution/src/api/request.ts`：把所有 `admin_token` 替换为 `institution_token`（localStorage 读取 + 401 清除处；登录跳转 `#/login` 保持）。

- [ ] **Step 5: auth store（单角色，调机构登录端点）**

`institution/src/stores/auth.ts`：

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import request, { unwrap } from '../api/request'
import type { TokenResponse } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('institution_token') || '')

  function isLoggedIn(): boolean { return !!token.value }

  async function login(username: string, password: string): Promise<void> {
    const data = await unwrap<TokenResponse>(
      request.post('/institution/auth/login', { username, password }),
    )
    token.value = data.access_token
    localStorage.setItem('institution_token', data.access_token)
  }

  function logout(): void {
    token.value = ''
    localStorage.removeItem('institution_token')
  }

  return { token, isLoggedIn, login, logout }
})
```

> 注：`types.ts` 需含 `TokenResponse`/`ApiResponse`（从 admin 复制已带）。

- [ ] **Step 6: Login.vue（机构登录页）**

`institution/src/views/Login.vue`：

```vue
<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function onSubmit() {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } catch (e) {
    ElMessage.error((e as Error).message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="t">机构管理后台</h2>
      <el-form @submit.prevent="onSubmit">
        <el-form-item><el-input v-model="form.username" placeholder="用户名" /></el-form-item>
        <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" show-password /></el-form-item>
        <el-button type="primary" :loading="loading" style="width:100%" @click="onSubmit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap { height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.login-card { width: 360px; }
.t { text-align: center; margin: 0 0 20px; }
</style>
```

（若 admin 的 Login.vue 结构更合适，可照搬其样式改标题与登录调用；以能登录为准。）

- [ ] **Step 7: MainLayout.vue（纯机构菜单）**

`institution/src/layouts/MainLayout.vue`：照搬 admin 的 MainLayout 结构，菜单**只留机构项**，无 role 判断：

```vue
<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'
const route = useRoute(); const router = useRouter(); const auth = useAuthStore()
const active = computed(() => route.path)
function onLogout() { auth.logout(); router.push('/login') }
</script>
<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="aside">
      <div class="logo">机构管理后台</div>
      <el-menu :default-active="active" router class="side-menu"
        background-color="#001529" text-color="rgba(255,255,255,0.75)" active-text-color="#fff">
        <el-menu-item index="/overview">机构概览</el-menu-item>
        <el-menu-item index="/profile">机构资料</el-menu-item>
        <el-menu-item index="/teachers">老师管理</el-menu-item>
        <el-menu-item index="/purchases">学生采购</el-menu-item>
        <el-menu-item index="/renew">批量续费</el-menu-item>
        <el-menu-item index="/bills">账单</el-menu-item>
        <el-menu-item index="/notifications">通知</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header"><span class="spacer" /><el-button text @click="onLogout">退出登录</el-button></el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>
<style scoped>
.aside { background: #001529; overflow: hidden; }
.logo { color: #fff; font-weight: 700; text-align: center; padding: 18px 0; font-size: 16px; }
.side-menu { width: 100%; border-right: none; }
.header { display: flex; align-items: center; background: #fff; border-bottom: 1px solid #eee; }
.spacer { flex: 1; }
</style>
```

- [ ] **Step 8: router（机构路由，无 role 分流）**

`institution/src/router/index.ts`：

```typescript
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', component: () => import('../views/InstitutionOverview.vue') },
        { path: 'profile', component: () => import('../views/InstitutionProfile.vue') },
        { path: 'teachers', component: () => import('../views/InstitutionTeachers.vue') },
        { path: 'purchases', component: () => import('../views/InstitutionPurchases.vue') },
        { path: 'renew', component: () => import('../views/InstitutionRenew.vue') },
        { path: 'bills', component: () => import('../views/InstitutionBills.vue') },
        { path: 'notifications', component: () => import('../views/Notifications.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn()) return { path: '/login' }
  if (to.path === '/login' && auth.isLoggedIn()) return { path: '/' }
  return true
})

export default router
```

> 注：迁移过来的 6 个 Institution*.vue 内部 import 路径是 `../api/institution`，已随复制保持有效；Notifications.vue import `../api/notifications` 同理。

- [ ] **Step 9: 安装依赖 + 构建**

Run: `cd frontend/institution && npm install && npm run build`
Expected: 构建成功。若 auto-imports.d.ts/components.d.ts 缺失导致类型报错，先 `npm run build` 由插件生成；仍报错则从 admin 复制这两个 .d.ts 占位后重建。

- [ ] **Step 10: Commit**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/institution
git commit -m "feat(institution-web): 新建独立机构前端应用（独立登录+机构菜单）"
```

---

## Task 4: admin web 收回机构页面

**Files:** `frontend/admin` 删 6 视图 + institution.ts、改 router/MainLayout/auth.ts

- [ ] **Step 1: 删除机构管理员视图 + api**

Run:
```bash
cd frontend/admin/src
rm views/InstitutionOverview.vue views/InstitutionProfile.vue views/InstitutionTeachers.vue views/InstitutionPurchases.vue views/InstitutionRenew.vue views/InstitutionBills.vue
rm api/institution.ts
```
（保留 `views/Institutions.vue`、`views/Notifications.vue`、`api/admin.ts`、`api/notifications.ts`。）

- [ ] **Step 2: router 去机构路由 + 去 role 分流**

`frontend/admin/src/router/index.ts`：删除所有 `institution/*` 子路由行；把 beforeEach 恢复为纯登录态守卫：

```typescript
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn()) return { path: '/login' }
  if (to.path === '/login' && auth.isLoggedIn()) return { path: '/' }
  return true
})
```
（保留 `institutions`(机构审核)、`notifications` 路由。）

- [ ] **Step 3: MainLayout 去机构菜单分支**

`frontend/admin/src/layouts/MainLayout.vue`：删除 `<template v-if="auth.role === 'institution_admin'">...</template>` 整块与外层 `v-else`，恢复为单一平台菜单：

```html
        <el-menu-item index="/overview">数据大盘</el-menu-item>
        <el-menu-item index="/questions">仿真题审核</el-menu-item>
        <el-menu-item index="/contents">知识点内容</el-menu-item>
        <el-menu-item index="/pricing">定价配置</el-menu-item>
        <el-menu-item index="/essay-templates">作文模板</el-menu-item>
        <el-menu-item index="/institutions">机构审核</el-menu-item>
        <el-menu-item index="/notifications">通知</el-menu-item>
```
（若 `auth.role` 不再被模板引用，可删除 script 中对应未用变量。）

- [ ] **Step 4: auth.ts 去 role 解码**

`frontend/admin/src/stores/auth.ts`：移除 `decodeRole`、`role` ref 与 `admin_role` 存取（菜单不再依赖 role），return 去掉 role。保留 token 登录（仍走 `/admin/auth/login`）。

- [ ] **Step 5: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功（无残留 import 机构视图/institution.ts）。若报某处仍 import 已删文件，按报错清除引用。

- [ ] **Step 6: Commit**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/admin
git commit -m "refactor(admin-web): 收回机构管理员页面/菜单/路由，登录仅平台超管"
```

---

## Task 5: 归档 D-129 + 清单同步

**Files:** `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部加 D-129（日期 2026-06-05 / 背景：机构与平台共用后台耦合面风险 / 结论：拆登录门 + 独立 institution 前端 + admin 收回 / 测试 / 影响范围 / 未做：独立域名部署 / 相关 D-120~128）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md`：部署节加「institution 前端单独构建/部署（dev 5175），与 admin web 分域名」；机构端 M 系列备注「机构管理员改在 institution 前端登录（/institution/auth/login）」。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-05-institution-web-split.md
git commit -m "docs: 归档 D-129 独立机构前端应用"
```

---

## Self-Review 结论

- **Spec 覆盖**：后端拆门+测试修正→Task1；回归→Task2；新前端→Task3；admin 收回→Task4；归档→Task5。全覆盖。
- **占位符**：无 TBD；后端代码完整；前端用 cp + 明确改动点（脚手架照搬属合理复用，非占位）。
- **类型一致**：`authenticate(allowed_roles)` 默认平台、机构端点传 institution_admin；两前端 token key 隔离（admin_token / institution_token）；institution 路由路径去掉 `institution/` 前缀（独立应用根路由），其 api 调用仍 `/api/v1/institution/*` 不变。
