# 作文精修深化：模板后台可配 + 跨篇进步分析 Implementation Plan（D-111）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 模板/范文运营后台可配（system_configs）+ 学生跨篇进步分析。

**Architecture:** 复用 SystemConfig（pricing 范式）存模板；essay_service 配置回落内置；get_progress 聚合 essays；admin web 加配置页；前端加进步卡片。

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 + PostgreSQL；uni-app Vue3（学生端）；Vue3 + Element Plus（admin web）。零迁移、dev-mock 无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、`../tests/...`、`-p no:randomly`。学生端 build：`frontend/miniprogram/` `npm run build:mp-weixin`。essay 测试沿用 autouse `monkeypatch essay_service.is_llm_dev_mode=True`。

---

## File Structure

| 文件 | 改动 |
|---|---|
| `backend/app/services/essay_service.py` | +get_configured_templates/get_all_templates_config/set_all_templates_config/get_progress/_ESSAY_TEMPLATES_KEY |
| `backend/app/schemas/essay.py` | +EssayTrendItem/EssayDimensionAvg/EssayProgressOut |
| `backend/app/api/v1/essay.py` | templates 改异步配置版 + progress endpoint（路由置前） |
| `backend/app/api/v1/admin.py` | essay-templates GET/PUT |
| `tests/services/test_essay_service.py`、`tests/api/test_essay.py`、`tests/api/test_admin_essay_templates.py`(新) | 测试 |
| 学生端 `pages/essay/index.vue`、`api/essay.ts`、`types/api.ts` | 进步卡片 |
| admin web `views/EssayTemplates.vue`、`api/admin.ts`、`router/index.ts`、`layouts/MainLayout.vue` | 模板配置页 |

---

## Task 1: service 配置化模板 + 进步聚合 + schemas

**Files:**
- Modify: `backend/app/services/essay_service.py`、`backend/app/schemas/essay.py`
- Test: `tests/services/test_essay_service.py`

- [ ] **Step 1: 写失败测试**

在 `tests/services/test_essay_service.py` 末尾追加：
```python
# ─── D-111: 配置化模板 + 进步聚合 ────────────────────────────────────

@pytest.mark.asyncio
async def test_configured_templates_fallback(db_session):
    # 未配置 → 回落内置
    t = await essay_service.get_configured_templates(db_session, "话题作文")
    assert t["template"] and len(t["samples"]) >= 1


@pytest.mark.asyncio
async def test_configured_templates_hit(db_session):
    from app.models.d9_system import SystemConfig
    db_session.add(SystemConfig(
        id=uuid.uuid4(), key="essay_templates",
        value={"话题作文": {"template": "自定义模板X", "samples": ["s1"]}, "_default": {"template": "兜底", "samples": ["d"]}},
    ))
    await db_session.flush()
    t = await essay_service.get_configured_templates(db_session, "话题作文")
    assert t["template"] == "自定义模板X"
    # 题型不存在 → _default
    t2 = await essay_service.get_configured_templates(db_session, "不存在题型")
    assert t2["template"] == "兜底"


@pytest.mark.asyncio
async def test_get_progress(db_session):
    sid = await _student(db_session, "promax")
    for _ in range(3):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="text", essay_type="话题作文")
    p = await essay_service.get_progress(db_session, student_id=sid)
    assert p["total_essays"] == 3
    assert p["avg_total"] == 88.0  # dev-mock 每维 22，总 88
    assert len(p["trend"]) == 3
    assert len(p["dimension_avg"]) == 4 and p["dimension_avg"][0]["avg"] == 22.0


@pytest.mark.asyncio
async def test_get_progress_empty(db_session):
    sid = await _student(db_session, "pro")
    p = await essay_service.get_progress(db_session, student_id=sid)
    assert p["total_essays"] == 0 and p["avg_total"] == 0 and p["trend"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: FAIL（`get_configured_templates`/`get_progress` 不存在）

- [ ] **Step 3: 实现 service**

在 `backend/app/services/essay_service.py` 顶部 import 区补：
```python
from app.models.d9_system import SystemConfig
```
在 `_MAX_ROUNDS = 5` 附近加：
```python
_ESSAY_TEMPLATES_KEY = "essay_templates"
```
在 `get_templates`（文件末尾内置常量函数）之后追加：
```python
async def get_configured_templates(db: AsyncSession, essay_type: str | None) -> dict:
    """读 system_configs.essay_templates；命中题型→用之，否则 _default，再否则回落内置。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        data = cfg.value
        if essay_type and essay_type in data:
            return data[essay_type]
        if "_default" in data:
            return data["_default"]
    return get_templates(essay_type)


async def get_all_templates_config(db: AsyncSession) -> dict:
    """admin 读：当前完整配置；未配则返回内置（含 _default）。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        return cfg.value
    return {**_TEMPLATES_BY_TYPE, "_default": _DEFAULT_TEMPLATE}


async def set_all_templates_config(db: AsyncSession, *, value: dict, admin_id: uuid.UUID) -> dict:
    """admin 写：upsert system_configs.essay_templates。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        cfg = SystemConfig(id=uuid.uuid4(), key=_ESSAY_TEMPLATES_KEY, value=value,
                           description="作文精修模板/范文（Module 5A）", updated_by=admin_id)
        db.add(cfg)
    else:
        cfg.value = value
        cfg.updated_by = admin_id
    await db.flush()
    return cfg.value


async def get_progress(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    rows = await list_essays(db, student_id=student_id)  # 倒序
    essays = list(reversed(rows))  # 时间正序
    total_essays = len(essays)
    totals = [(e.dimensions or {}).get("total", 0) for e in essays]
    avg_total = round(sum(totals) / total_essays, 1) if total_essays else 0
    trend = [{"date": e.created_at.date().isoformat(), "total": (e.dimensions or {}).get("total", 0)} for e in essays]
    dim_sum: dict[str, list[int]] = {}
    for e in essays:
        for s in (e.dimensions or {}).get("scores", []):
            dim_sum.setdefault(s["dimension"], []).append(s["score"])
    dimension_avg = [{"dimension": d, "avg": round(sum(v) / len(v), 1)} for d, v in dim_sum.items()]
    return {
        "total_essays": total_essays,
        "avg_total": avg_total,
        "trend": trend,
        "dimension_avg": dimension_avg,
    }
```
在 `backend/app/schemas/essay.py` 追加：
```python
class EssayTrendItem(BaseModel):
    date: str
    total: int


class EssayDimensionAvg(BaseModel):
    dimension: str
    avg: float


class EssayProgressOut(BaseModel):
    total_essays: int
    avg_total: float
    trend: list[EssayTrendItem]
    dimension_avg: list[EssayDimensionAvg]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: PASS（D-109/110 + D-111 4 例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/essay_service.py backend/app/schemas/essay.py tests/services/test_essay_service.py
git commit -m "feat(backend): 作文模板配置化 get_configured_templates + 跨篇进步 get_progress"
```

---

## Task 2: 学生 API progress + templates 配置版 + admin API

**Files:**
- Modify: `backend/app/api/v1/essay.py`、`backend/app/api/v1/admin.py`
- Test: `tests/api/test_essay.py`、`tests/api/test_admin_essay_templates.py`（新）

- [ ] **Step 1: 写失败测试**

在 `tests/api/test_essay.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_progress_via_api(client):
    headers = await _login_pro(client, uuid.uuid4().hex[:6])
    for _ in range(2):
        await client.post("/api/v1/essays", json={"original_text": "t", "essay_type": "话题作文"}, headers=headers)
    r = await client.get("/api/v1/essays/progress", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_essays"] == 2 and len(data["trend"]) == 2
```

创建 `tests/api/test_admin_essay_templates.py`（复刻 test_admin_pricing 的 admin helper + cleanup）：
```python
"""运营 admin 作文模板配置测试（D-111）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"admine_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == f"admine_{suffix}"))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _cleanup() -> None:
    from app.models.d9_system import SystemConfig
    async with _async_session_factory() as s:
        cfg = (await s.execute(
            select(SystemConfig).where(SystemConfig.key == "essay_templates")
        )).scalar_one_or_none()
        if cfg is not None:
            await s.delete(cfg)
            await s.commit()


@pytest.mark.asyncio
async def test_admin_get_update_essay_templates(client):
    headers = await _make_admin(client, uuid.uuid4().hex[:6])
    try:
        # 默认返回内置（含 _default）
        r0 = await client.get("/api/v1/admin/essay-templates", headers=headers)
        assert r0.status_code == 200 and "_default" in r0.json()["data"]
        # PUT 自定义
        payload = {"话题作文": {"template": "运营模板", "samples": ["a", "b", "c"]}, "_default": {"template": "兜底", "samples": ["d"]}}
        r1 = await client.put("/api/v1/admin/essay-templates", json=payload, headers=headers)
        assert r1.status_code == 200
        r2 = await client.get("/api/v1/admin/essay-templates", headers=headers)
        assert r2.json()["data"]["话题作文"]["template"] == "运营模板"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_admin_templates_requires_admin(client):
    # 普通用户（非 admin）→ 403
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"normal_{uuid.uuid4().hex[:6]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    r = await client.get("/api/v1/admin/essay-templates", headers=headers)
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py::test_progress_via_api ../tests/api/test_admin_essay_templates.py -p no:randomly -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 改学生 essay API**

编辑 `backend/app/api/v1/essay.py`：
1. import 区补 `EssayProgressOut`：
```python
from app.schemas.essay import (
    EssayCreate, EssayListItem, EssayListOut, EssayOut,
    EssayProgressOut, EssayRoundItem, EssayTemplatesOut, RepolishIn,
)
```
2. `essay_templates` endpoint 内把 `t = essay_service.get_templates(essay_type)` 改为：
```python
    t = await essay_service.get_configured_templates(db, essay_type)
```
3. 在 `/templates` endpoint 之后、`/{essay_id}` 之前，新增 progress（同样置于 `/{essay_id}` 前）：
```python
@router.get("/progress", response_model=BaseResponse[EssayProgressOut])
async def my_progress(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    return make_ok(EssayProgressOut(**await essay_service.get_progress(db, student_id=current_user.id)))
```

- [ ] **Step 4: 加 admin API**

编辑 `backend/app/api/v1/admin.py`：
1. import 区确保有 `from app.services import essay_service`（若无则加；admin.py 已 import 多个 service，按现有风格加）。
2. 在 pricing endpoints 之后追加：
```python
@router.get("/essay-templates", response_model=BaseResponse[dict])
async def get_essay_templates(db: DbDep, admin: AdminDep):
    return make_ok(await essay_service.get_all_templates_config(db))


@router.put("/essay-templates", response_model=BaseResponse[dict])
async def update_essay_templates(body: dict, db: DbDep, admin: AdminDep):
    v = await essay_service.set_all_templates_config(db, value=body, admin_id=admin.id)
    await db.commit()
    return make_ok(v)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py ../tests/api/test_admin_essay_templates.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/essay.py backend/app/api/v1/admin.py tests/api/test_essay.py tests/api/test_admin_essay_templates.py
git commit -m "feat(backend): 学生 essay 进步 API + 模板配置版 + admin 模板 GET/PUT"
```

---

## Task 3: admin web 作文模板配置页

**Files:**
- Modify: `frontend/admin/src/api/admin.ts`、`router/index.ts`、`layouts/MainLayout.vue`
- Create: `frontend/admin/src/views/EssayTemplates.vue`

- [ ] **Step 1: 加 admin api**

`frontend/admin/src/api/admin.ts` 末尾追加：
```typescript
export function getEssayTemplates() {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.get('/admin/essay-templates'))
}
export function updateEssayTemplates(payload: Record<string, { template: string; samples: string[] }>) {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.put('/admin/essay-templates', payload))
}
```

- [ ] **Step 2: 建 EssayTemplates.vue**

创建 `frontend/admin/src/views/EssayTemplates.vue`：
```vue
<template>
  <div class="page">
    <h2>作文模板 / 范文配置</h2>
    <p class="hint">按题型配置模板与范文（每行一条范文）。键 _default 为兜底。</p>
    <el-card v-for="(item, key) in form" :key="key" class="tpl-card">
      <template #header>
        <div class="card-head">
          <span>{{ key }}</span>
          <el-button size="small" type="danger" link @click="removeKey(key)">删除</el-button>
        </div>
      </template>
      <el-input v-model="item.template" type="textarea" :rows="3" placeholder="模板" />
      <el-input v-model="item.samplesText" type="textarea" :rows="4" placeholder="范文（每行一条）" style="margin-top: 8px" />
    </el-card>

    <div class="add-row">
      <el-input v-model="newKey" placeholder="新增题型（如 议论文 / _default）" style="width: 240px" />
      <el-button @click="addKey">添加题型</el-button>
    </div>

    <el-button type="primary" :loading="saving" @click="save">保存</el-button>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getEssayTemplates, updateEssayTemplates } from '../api/admin'

type Item = { template: string; samplesText: string }
const form = reactive<Record<string, Item>>({})
const newKey = ref('')
const saving = ref(false)

onMounted(async () => {
  const data = await getEssayTemplates()
  for (const [k, v] of Object.entries(data)) {
    form[k] = { template: v.template, samplesText: (v.samples || []).join('\n') }
  }
})

function addKey() {
  const k = newKey.value.trim()
  if (!k || form[k]) return
  form[k] = { template: '', samplesText: '' }
  newKey.value = ''
}
function removeKey(k: string) { delete form[k] }

async function save() {
  saving.value = true
  try {
    const payload: Record<string, { template: string; samples: string[] }> = {}
    for (const [k, v] of Object.entries(form)) {
      payload[k] = { template: v.template, samples: v.samplesText.split('\n').map((s) => s.trim()).filter(Boolean) }
    }
    await updateEssayTemplates(payload)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page { padding: 16px; }
.hint { color: #888; font-size: 13px; margin-bottom: 12px; }
.tpl-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.add-row { display: flex; gap: 8px; margin: 16px 0; }
</style>
```

- [ ] **Step 3: 注册 router + 菜单**

`frontend/admin/src/router/index.ts`：在 children 数组（pricing 之后）加：
```typescript
        { path: 'essay-templates', name: 'essay-templates', component: () => import('../views/EssayTemplates.vue') },
```
`frontend/admin/src/layouts/MainLayout.vue`：在 `<el-menu-item index="/pricing">定价配置</el-menu-item>` 之后加：
```html
        <el-menu-item index="/essay-templates">作文模板</el-menu-item>
```

- [ ] **Step 4: admin web 构建验证**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功（若该项目 npm 不可用/未装依赖，则跳过并记录——以 tsc/vite 能跑为准；不可用时仅做人工检查）。

> 若 admin web 依赖未安装/无法构建（与项目 npm 现状有关），本步以「文件就位 + 代码自检」为准，构建留待环境就绪。

- [ ] **Step 5: 提交**

```bash
git add frontend/admin/src/api/admin.ts frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue frontend/admin/src/views/EssayTemplates.vue
git commit -m "feat(admin): 作文模板/范文配置页"
```

---

## Task 4: 学生端进步卡片

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`、`api/essay.ts`、`pages/essay/index.vue`

- [ ] **Step 1: 加类型**

`types/api.ts` essay 区追加：
```typescript
export interface EssayTrendItem { date: string; total: number }
export interface EssayDimensionAvg { dimension: string; avg: number }
export interface EssayProgress {
  total_essays: number
  avg_total: number
  trend: EssayTrendItem[]
  dimension_avg: EssayDimensionAvg[]
}
```

- [ ] **Step 2: 加 api**

`api/essay.ts`：import 类型补 `EssayProgress`，末尾追加：
```typescript
export function getEssayProgress(): Promise<EssayProgress> {
  return request<EssayProgress>('/api/v1/essays/progress', { method: 'GET' })
}
```

- [ ] **Step 3: index.vue 进步卡片**

编辑 `frontend/miniprogram/src/pages/essay/index.vue`：
(a) import + ref：
```typescript
import { createEssay, getEssays, getEssayProgress } from '@/api/essay'
import type { EssayListItem, EssayProgress } from '@/types/api'
```
```typescript
const progress = ref<EssayProgress | null>(null)
```
(b) `loadList` 内或 onShow 追加拉取：
```typescript
async function loadProgress() {
  try { progress.value = await getEssayProgress() } catch { /* 忽略 */ }
}
```
并在 `onShow(loadList)` 改为同时拉：
```typescript
onShow(() => { loadList(); loadProgress() })
```
(c) 模板顶部（第一个 card 之前）插入进步卡片：
```html
    <view v-if="progress && progress.total_essays > 0" class="card">
      <view class="card-title">我的进步</view>
      <view class="prog-row">
        <text>已精修 {{ progress.total_essays }} 篇</text>
        <text class="prog-avg">平均 {{ progress.avg_total }} 分</text>
      </view>
      <view v-for="d in progress.dimension_avg" :key="d.dimension" class="prog-dim">
        <text>{{ d.dimension }}</text><text class="prog-avg">{{ d.avg }}</text>
      </view>
    </view>
```
(d) 样式追加：
```css
.prog-row { display: flex; justify-content: space-between; font-size: 28rpx; color: var(--c-text-body); margin-bottom: 8rpx; }
.prog-avg { font-weight: 700; color: var(--c-gold); }
.prog-dim { display: flex; justify-content: space-between; font-size: 26rpx; color: var(--c-text-second); padding: 4rpx 0; }
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/api/essay.ts frontend/miniprogram/src/pages/essay/index.vue
git commit -m "feat(frontend): 作文精修首页 我的进步卡片"
```

---

## Task 5: 全量回归 + 归档 D-111

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 425 passed；净增约 7 例。已知 flaky test_get_wrong_question_api 若失败隔离重跑确认）

- [ ] **Step 2: 学生端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-111**

在 `docs/决策归档.md` 顶部（`## D-110` 之前）插入 D-111：日期、背景、结论（模板存 system_configs.essay_templates + get_configured_templates 回落内置 + admin GET/PUT + get_progress 聚合 + 学生 progress API 路由置前 + admin web 配置页 + 前端进步卡片）、测试（强制 dev-mock；后端全量 passed + 学生端 build）、影响范围、未做（模板富文本/范文AI生成/进步图表/档位差异化模板）、相关（D-109/110、pricing_service、Module 5A/5.7）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-111 作文模板后台可配 + 跨篇进步分析"
```

- [ ] **Step 5: 询问用户是否 push**

报告 commit 列表 + 测试/构建结果，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- 模板配置化（get_configured_templates 回落 / admin get/set）→ Task 1+2 ✓
- 跨篇进步（get_progress 聚合 + 学生 API）→ Task 1+2 ✓
- 路由顺序（progress/templates 在 /{essay_id} 前）→ Task 2 Step 3 ✓
- admin web 配置页 → Task 3 ✓
- 前端进步卡片 → Task 4 ✓
- 零迁移、dev-mock 强制 → 全程 ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。admin web 构建步给了「依赖不可用则文件就位+自检」的明确兜底（非占位）。

**3. 类型一致：** `get_progress` 返回键 total_essays/avg_total/trend/dimension_avg 与 `EssayProgressOut` 一致；`get_configured_templates` 返回 {template,samples} 与 `EssayTemplatesOut`/前端一致；admin GET/PUT 用 dict（题型→{template,samples}）前后端一致；`admin.id`（AdminDep=User）与 set_all_templates_config 的 admin_id 一致；学生端 `EssayProgress` 与后端对齐。
