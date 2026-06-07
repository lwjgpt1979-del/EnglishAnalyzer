# V2 M3c：旧练习路径迁移 + 学习闭环打通 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for all implementation steps.

**Goal:** 新增 KP 搜索 API，重写 `practice/index.vue` 为 V2 调度页，打通学习闭环。

**Design Ref:** `docs/superpowers/specs/2026-06-07-v2-m3c-practice-migration-design.md`

**Tech Stack:** FastAPI + SQLAlchemy asyncio（后端），Vue3/uni-app（前端），pytest-asyncio

---

## 文件地图

| 操作 | 文件 | 责任 |
|---|---|---|
| 新建 | `tests/services/test_curriculum_kp_search.py` | search_kps service 单元测试（先写） |
| 新建 | `tests/api/test_curriculum_kp_search.py` | KP 搜索端点集成测试（先写） |
| 修改 | `backend/app/schemas/curriculum.py` | 新增 `KPSearchItem` |
| 修改 | `backend/app/services/curriculum_service.py` | 新增 `search_kps()` |
| 修改 | `backend/app/api/v1/curriculum.py` | 新增 `GET /kps/search` |
| 新建 | `frontend/miniprogram/src/api/curriculum_kps.ts` | `searchKPs()` |
| 修改 | `frontend/miniprogram/src/types/api.ts` | `KPSearchItem` 类型 |
| 重写 | `frontend/miniprogram/src/pages/practice/index.vue` | V2 调度页 |

---

## Task 1：后端 — search_kps service（TDD）

**目标**：在 `curriculum_service.py` 新增 `search_kps(db, q, limit)` 函数，按名称模糊搜索知识点。

**Files:**
- Create: `tests/services/test_curriculum_kp_search.py`
- Modify: `backend/app/services/curriculum_service.py`
- Modify: `backend/app/schemas/curriculum.py`

### Step 1: 写 service 测试（RED）

新建 `tests/services/test_curriculum_kp_search.py`：

```python
"""search_kps service TDD 测试。"""
from __future__ import annotations
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
import uuid


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seed_kps(db: AsyncSession):
    """插入 4 个知识点：2 个含"完成"，1 个含"被动"，1 个其他。"""
    kps = [
        KnowledgePoint(id=uuid.uuid4(), name="现在完成时", category="grammar"),
        KnowledgePoint(id=uuid.uuid4(), name="过去完成时", category="grammar"),
        KnowledgePoint(id=uuid.uuid4(), name="被动语态",   category="grammar"),
        KnowledgePoint(id=uuid.uuid4(), name="一般现在时", category="grammar"),
    ]
    for k in kps:
        db.add(k)
    await db.flush()
    return kps


@pytest.mark.asyncio
async def test_search_kps_by_keyword(db, seed_kps):
    """关键词"完成"应返回2条，不含"被动"和"一般"。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="完成", limit=10)
    names = [r.name for r in results]
    assert len(results) == 2
    assert "现在完成时" in names
    assert "过去完成时" in names
    assert "被动语态" not in names


@pytest.mark.asyncio
async def test_search_kps_empty_query_returns_all(db, seed_kps):
    """空字符串不过滤，返回 limit 条。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="", limit=10)
    assert len(results) >= 4


@pytest.mark.asyncio
async def test_search_kps_no_match_returns_empty(db, seed_kps):
    """无匹配时返回空列表，不报错。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="不可能存在的知识点XYZ", limit=10)
    assert results == []


@pytest.mark.asyncio
async def test_search_kps_respects_limit(db, seed_kps):
    """limit 参数生效：limit=2 最多返回 2 条。"""
    from app.services.curriculum_service import search_kps
    results = await search_kps(db, q="", limit=2)
    assert len(results) <= 2
```

### Step 2: 确认 RED

```bash
cd backend
python3 -c "from app.services.curriculum_service import search_kps" 2>&1
# 预期：ImportError（search_kps 不存在）
```

### Step 3: 新增 `KPSearchItem` schema

`backend/app/schemas/curriculum.py` 末尾加：

```python
class KPSearchItem(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None = None
```

### Step 4: 实现 `search_kps`

`backend/app/services/curriculum_service.py` 末尾加：

```python
async def search_kps(
    db: AsyncSession,
    *,
    q: str,
    limit: int = 10,
) -> list[KnowledgePoint]:
    """按名称模糊搜索知识点（ILIKE）。q 为空则不过滤，返回前 limit 条。"""
    stmt = select(KnowledgePoint).order_by(KnowledgePoint.name)
    if q:
        stmt = stmt.where(KnowledgePoint.name.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())
```

需在文件顶部确认已 import `select`（已有）和 `KnowledgePoint`（已有）。

### Step 5: 运行测试确认 GREEN

```bash
python3 -c "
from app.services.curriculum_service import search_kps
print('search_kps import OK')
"
```

### Step 6: Commit

```bash
git add backend/app/schemas/curriculum.py \
        backend/app/services/curriculum_service.py \
        tests/services/test_curriculum_kp_search.py
git commit -m "feat(v2): search_kps service + KPSearchItem schema（TDD）"
```

---

## Task 2：后端 — KP 搜索 API 端点（TDD）

**目标**：新增 `GET /api/v1/curriculum/kps/search` 端点。

**Files:**
- Create: `tests/api/test_curriculum_kp_search.py`
- Modify: `backend/app/api/v1/curriculum.py`

### Step 1: 写 API 测试（RED）

新建 `tests/api/test_curriculum_kp_search.py`：

```python
"""KP 搜索 API 集成测试（TDD）。"""
from __future__ import annotations
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_kp_search_returns_200(client: AsyncClient):
    """GET /curriculum/kps/search 无参数时返回 200 + list。"""
    resp = await client.get("/api/v1/curriculum/kps/search")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_kp_search_with_keyword(client: AsyncClient):
    """q 参数被接受，返回 200。"""
    resp = await client.get("/api/v1/curriculum/kps/search", params={"q": "完成时"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    for item in data:
        assert "id" in item
        assert "name" in item
        assert "完成时" in item["name"]


@pytest.mark.asyncio
async def test_kp_search_limit_validation(client: AsyncClient):
    """limit > 20 时返回 422。"""
    resp = await client.get("/api/v1/curriculum/kps/search", params={"limit": 25})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_kp_search_no_answer_leak(client: AsyncClient):
    """返回数据不含 answer 等敏感字段。"""
    resp = await client.get("/api/v1/curriculum/kps/search")
    assert resp.status_code == 200
    for item in resp.json()["data"]:
        assert "answer" not in item
        assert "content_md" not in item
```

### Step 2: 确认 RED（端点不存在 → 404）

```bash
python3 -c "
from app.api.v1.curriculum import router
routes = [r.path for r in router.routes]
print(routes)
assert '/curriculum/kps/search' not in routes
print('RED confirmed: route missing')
"
```

### Step 3: 实现端点

`backend/app/api/v1/curriculum.py` 中，在现有路由末尾添加：

```python
@router.get("/kps/search")
async def search_knowledge_points(
    db: DbDep,
    q: str = Query("", description="搜索关键词（知识点名称模糊匹配）"),
    limit: int = Query(10, ge=1, le=20, description="最多返回条数"),
):
    """按知识点名称模糊搜索，供前端选择目标 KP。无需会员。"""
    kps = await curriculum_service.search_kps(db, q=q, limit=limit)
    from app.schemas.curriculum import KPSearchItem
    return make_ok([
        KPSearchItem(
            id=kp.id,
            name=kp.name,
            category=str(kp.category),
            description=kp.description,
        ).model_dump(mode="json")
        for kp in kps
    ])
```

确认顶部 import 有 `Query`（已有）和 `curriculum_service`（已有）。

### Step 4: 验证 GREEN

```bash
python3 -c "
from app.api.v1.curriculum import router
routes = [r.path for r in router.routes]
assert '/curriculum/kps/search' in routes
print('GREEN: /curriculum/kps/search 已注册')
"
```

### Step 5: Commit

```bash
git add backend/app/api/v1/curriculum.py \
        tests/api/test_curriculum_kp_search.py
git commit -m "feat(v2): GET /curriculum/kps/search 端点（TDD）"
```

---

## Task 3：前端 — KP 搜索 API + 类型

**目标**：新建 `api/curriculum_kps.ts`，在 `types/api.ts` 加 `KPSearchItem`。

**Files:**
- Create: `frontend/miniprogram/src/api/curriculum_kps.ts`
- Modify: `frontend/miniprogram/src/types/api.ts`

### Step 1: 添加 TypeScript 类型

`frontend/miniprogram/src/types/api.ts` 末尾加：

```typescript
export interface KPSearchItem {
  id: string
  name: string
  category: string
  description: string | null
}
```

### Step 2: 新建 API 文件

新建 `frontend/miniprogram/src/api/curriculum_kps.ts`：

```typescript
import { request } from '@/utils/request'
import type { KPSearchItem } from '@/types/api'

export function searchKPs(q = '', limit = 10): Promise<KPSearchItem[]> {
  return request<KPSearchItem[]>('/api/v1/curriculum/kps/search', {
    method: 'GET',
    data: { q, limit },
  })
}
```

### Step 3: Commit

```bash
git add frontend/miniprogram/src/api/curriculum_kps.ts \
        frontend/miniprogram/src/types/api.ts
git commit -m "feat(miniprogram): KPSearchItem 类型 + searchKPs API 函数"
```

---

## Task 4：前端 — 重写 `practice/index.vue`

**目标**：将 V1 入口改为 V2 调度页（搜索 KP → v2-session，或智能出题 → adaptive）。

**Files:**
- Rewrite: `frontend/miniprogram/src/pages/practice/index.vue`

### Step 1: 了解现有页面结构

```bash
wc -l frontend/miniprogram/src/pages/practice/index.vue
grep -n "phase\|generateQuestions\|submitAnswer" frontend/miniprogram/src/pages/practice/index.vue | head -10
```

### Step 2: 重写页面

将 `frontend/miniprogram/src/pages/practice/index.vue` 完整替换为：

```vue
<!-- V2 M3c: 练习调度页 — 搜索知识点或使用 AI 智能推荐 -->
<template>
  <view class="page">
    <!-- 搜索区 -->
    <view class="card search-card">
      <view class="card-title">选择知识点练习</view>
      <view class="search-row">
        <input
          v-model="query"
          class="search-input"
          placeholder="搜索知识点，如：现在完成时"
          @input="onInput"
          @confirm="doSearch"
        />
        <button class="btn-search" @tap="doSearch">搜索</button>
      </view>

      <!-- 搜索结果 -->
      <view v-if="searching" class="hint">搜索中…</view>
      <view v-else-if="results.length" class="result-list">
        <view
          v-for="kp in results"
          :key="kp.id"
          class="result-item"
          @tap="goSession(kp)"
        >
          <view class="result-main">
            <text class="result-name">{{ kp.name }}</text>
            <text class="result-cat">{{ kp.category }}</text>
          </view>
          <text class="result-arrow">›</text>
        </view>
      </view>
      <view v-else-if="searched && !results.length" class="hint">
        未找到匹配知识点，换个关键词试试
      </view>
    </view>

    <!-- 分割线 -->
    <view class="divider">
      <view class="divider-line" /><text class="divider-text">或</text><view class="divider-line" />
    </view>

    <!-- AI 智能推荐 -->
    <view class="card ai-card" @tap="goAdaptive">
      <view class="ai-left">
        <text class="ai-icon">🤖</text>
        <view>
          <text class="ai-title">AI 帮我选</text>
          <text class="ai-desc">基于薄弱点智能推荐题目</text>
        </view>
      </view>
      <text class="ai-arrow">›</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { searchKPs } from '@/api/curriculum_kps'
import type { KPSearchItem } from '@/types/api'

const query = ref('')
const results = ref<KPSearchItem[]>([])
const searching = ref(false)
const searched = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!query.value.trim()) {
    results.value = []
    searched.value = false
    return
  }
  debounceTimer = setTimeout(doSearch, 400)
}

async function doSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    results.value = await searchKPs(query.value.trim(), 10)
    searched.value = true
  } catch {
    uni.showToast({ title: '搜索失败，请重试', icon: 'none' })
  } finally {
    searching.value = false
  }
}

function goSession(kp: KPSearchItem) {
  uni.navigateTo({
    url: `/pages/practice/v2-session?kp=${kp.id}&dim=grammar`,
  })
}

function goAdaptive() {
  uni.navigateTo({ url: '/pages/practice/adaptive' })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }

.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4);
        box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 24rpx; }
.card-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 20rpx; display: block; }

.search-row { display: flex; gap: 12rpx; margin-bottom: 16rpx; }
.search-input { flex: 1; border: 2rpx solid var(--c-border); border-radius: var(--r-md);
                height: 72rpx; line-height: 72rpx; padding: 0 20rpx; font-size: 28rpx; }
.btn-search { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-md);
              padding: 0 28rpx; font-size: 26rpx; font-weight: 600; height: 72rpx;
              line-height: 72rpx; white-space: nowrap; }

.hint { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 16rpx 0; }

.result-list { display: flex; flex-direction: column; gap: 2rpx; }
.result-item { display: flex; align-items: center; justify-content: space-between;
               padding: 20rpx 12rpx; border-bottom: 1rpx solid var(--c-border); }
.result-item:last-child { border-bottom: none; }
.result-main { display: flex; flex-direction: column; gap: 4rpx; }
.result-name { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.result-cat { font-size: 22rpx; color: var(--c-text-hint); }
.result-arrow { font-size: 36rpx; color: var(--c-text-hint); }

.divider { display: flex; align-items: center; gap: 16rpx; margin: 8rpx 0 24rpx; }
.divider-line { flex: 1; height: 1rpx; background: var(--c-border); }
.divider-text { font-size: 24rpx; color: var(--c-text-hint); white-space: nowrap; }

.ai-card { display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
.ai-left { display: flex; align-items: center; gap: 20rpx; }
.ai-icon { font-size: 56rpx; }
.ai-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); display: block; }
.ai-desc { font-size: 24rpx; color: var(--c-text-second); display: block; margin-top: 4rpx; }
.ai-arrow { font-size: 40rpx; color: var(--c-text-hint); }
</style>
```

### Step 3: 验证无旧 API 调用

```bash
grep "generateQuestions\|submitAnswer\|api/practice" \
  frontend/miniprogram/src/pages/practice/index.vue
# 预期：无输出
```

### Step 4: Commit

```bash
git add frontend/miniprogram/src/pages/practice/index.vue
git commit -m "feat(miniprogram): practice/index 重写为 V2 调度页（KP 搜索 + AI 推荐）"
```

---

## Task 5：归档 + 整体验证

### Step 1: 后端导入链验证

```bash
cd backend
python3 -c "
from app.services.curriculum_service import search_kps
from app.api.v1.curriculum import router
from app.schemas.curriculum import KPSearchItem
routes = [r.path for r in router.routes]
assert '/curriculum/kps/search' in routes
print('✅ search_kps service OK')
print('✅ /curriculum/kps/search 路由 OK')
print('✅ KPSearchItem schema OK')
"
```

### Step 2: 确认旧 practice API 调用已清除

```bash
grep -rn "generateQuestions\|submitAnswer" \
  frontend/miniprogram/src/pages/ --include="*.vue"
# 预期：无输出（只有 api/practice.ts 文件本身可以保留）
```

### Step 3: 提交文档

```bash
git add docs/superpowers/specs/2026-06-07-v2-m3c-practice-migration-design.md \
        docs/superpowers/plans/2026-06-07-v2-m3c-practice-migration-plan.md
git commit -m "docs: V2 M3c 旧练习路径迁移设计文档 + 实施计划"
```

### Step 4: 最终 commit 汇总

```bash
git log --oneline -6
```
确认 4 个 feature commit + 1 个 docs commit 均已落地。

---

## 执行顺序

```
Task 1（search_kps service）→ Task 2（API 端点）← 依赖 Task 1
Task 3（前端类型 + API）← 可与 Task 1/2 并行
Task 4（前端重写）← 依赖 Task 3
Task 5（验证 + 归档）← 依赖 1-4
```
