# D-130 AI 智能出题 + 内容完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for all implementation steps. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补写 D-130 AI 智能出题的配套 API 测试，修复 3 处 bug（kp-content 维度 tab、诊断页跳转、首页快捷入口），提交存档。

**Design Ref:** `docs/superpowers/specs/2026-06-07-d130-adaptive-questions-design.md`

**Tech Stack:** FastAPI + pytest-asyncio（后端），Vue3/uni-app（前端）

---

## 文件地图

| 操作 | 文件 | 责任 |
|---|---|---|
| 新建 | `tests/api/test_adaptive_api.py` | adaptive-set 端点集成测试 |
| 修改 | `frontend/miniprogram/src/pages/curriculum/kp-content.vue` | dims 4→6 维度 |
| 修改 | `frontend/miniprogram/src/pages/diagnosis/index.vue` | goPractice 跳转修正 |
| 修改 | `frontend/miniprogram/src/pages/index/index.vue` | 首页加"智能出题"入口 |

---

## Task 1：补写 adaptive-set API 测试

**目标**：为 `GET /api/v1/questions/adaptive-set` 补集成测试，验证返回结构不含 answer 字段（防作弊）。

**Files:**
- Create: `tests/api/test_adaptive_api.py`

- [ ] **Step 1: 查看已有 API 测试的 conftest 与模式**

  ```bash
  cat tests/api/conftest.py | head -60
  cat tests/api/test_questions.py | head -40
  ```
  理解 `client` fixture、token 注入方式、`make_ok` 响应结构。

- [ ] **Step 2: 写测试文件（先 RED）**

  新建 `tests/api/test_adaptive_api.py`：

  ```python
  """D-130 adaptive-set API 集成测试。

  TDD：先写测试 → 确认失败 → 实现已存在（只需验证行为）→ GREEN
  """
  from __future__ import annotations

  import pytest
  from httpx import AsyncClient


  @pytest.mark.asyncio
  async def test_adaptive_set_returns_200_with_empty_data(client: AsyncClient, auth_headers: dict):
      """无错题时返回 200，questions 为空列表，weak_kp_names 为空。"""
      resp = await client.get("/api/v1/questions/adaptive-set", headers=auth_headers)
      assert resp.status_code == 200
      data = resp.json()["data"]
      assert "questions" in data
      assert "weak_kp_names" in data
      assert isinstance(data["questions"], list)
      assert isinstance(data["weak_kp_names"], list)


  @pytest.mark.asyncio
  async def test_adaptive_set_questions_have_no_answer_field(client: AsyncClient, auth_headers: dict):
      """返回的每道题不含 answer 字段（防作弊）。"""
      resp = await client.get("/api/v1/questions/adaptive-set", headers=auth_headers)
      assert resp.status_code == 200
      questions = resp.json()["data"]["questions"]
      for q in questions:
          assert "answer" not in q, f"题目 {q.get('id')} 泄露了 answer 字段"


  @pytest.mark.asyncio
  async def test_adaptive_set_requires_auth(client: AsyncClient):
      """未携带 token 时返回 401。"""
      resp = await client.get("/api/v1/questions/adaptive-set")
      assert resp.status_code == 401


  @pytest.mark.asyncio
  async def test_adaptive_set_total_param_respected(client: AsyncClient, auth_headers: dict):
      """total 参数被尊重（返回题数 ≤ total）。"""
      resp = await client.get(
          "/api/v1/questions/adaptive-set",
          params={"total": 3},
          headers=auth_headers,
      )
      assert resp.status_code == 200
      questions = resp.json()["data"]["questions"]
      assert len(questions) <= 3
  ```

- [ ] **Step 3: 运行测试，确认 RED 或 GREEN**

  ```bash
  cd backend
  python -m pytest ../tests/api/test_adaptive_api.py -v
  ```
  - 如果 conftest 的 `auth_headers` fixture 不存在，查看 `tests/api/conftest.py` 里实际 fixture 名称，调整测试文件。
  - 预期：`test_adaptive_set_requires_auth` 和 `test_adaptive_set_returns_200_with_empty_data` PASS（服务已实现）；其余视 conftest 而定。

- [ ] **Step 4: 修正 fixture 名称（如需要）**

  如测试 fixture 名与 conftest 不符，对齐后重跑直到全 PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tests/api/test_adaptive_api.py
  git commit -m "test(d130): adaptive-set API 集成测试（无答案字段/鉴权/total 参数）"
  ```

---

## Task 2：修复 kp-content.vue 维度 tab（4→6）

**目标**：将 `kp-content.vue` 的 `dims` 数组从旧 4 个维度（含 dictation）更新为新 6 个维度（去 dictation，加 vocabulary/reading/translation）。

**Files:**
- Modify: `frontend/miniprogram/src/pages/curriculum/kp-content.vue`

**背景**：migration 0022 已在数据库中把 `content_dimension` 从 4 改为 6，后端 AI service 已生成新维度的内容，只有前端 tab 未同步。

- [ ] **Step 1: 定位 dims 数组**

  ```bash
  grep -n "dictation\|dims\|listening" frontend/miniprogram/src/pages/curriculum/kp-content.vue
  ```
  找到 `const dims = [...]` 的行号。

- [ ] **Step 2: 修改 dims（RED → GREEN 在浏览器/devtool 层面验证）**

  将：
  ```typescript
  const dims = [
    { key: 'listening', label: '听力' },
    { key: 'dictation', label: '听写' },
    { key: 'grammar',   label: '语法' },
    { key: 'writing',   label: '写作' },
  ]
  ```
  改为：
  ```typescript
  const dims = [
    { key: 'listening',   label: '听力' },
    { key: 'vocabulary',  label: '词汇' },
    { key: 'grammar',     label: '语法' },
    { key: 'reading',     label: '阅读' },
    { key: 'translation', label: '翻译' },
    { key: 'writing',     label: '写作' },
  ]
  ```
  `activeDim` 默认值 `'grammar'` 不变（grammar 在新枚举中仍存在）。

- [ ] **Step 3: 验证无 TypeScript 错误**

  ```bash
  cd frontend/miniprogram
  npx vue-tsc --noEmit 2>&1 | grep -i "kp-content\|error" | head -10
  ```
  预期：无 kp-content 相关报错。

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/miniprogram/src/pages/curriculum/kp-content.vue
  git commit -m "fix(miniprogram): kp-content 维度 tab 同步到 6 个（去 dictation + 词汇/阅读/翻译）"
  ```

---

## Task 3：修复诊断页"智能练习"跳转

**目标**：`diagnosis/index.vue` 的 `goPractice()` 改为跳转到 `/pages/practice/adaptive`。

**Files:**
- Modify: `frontend/miniprogram/src/pages/diagnosis/index.vue`

- [ ] **Step 1: 定位 goPractice 函数**

  ```bash
  grep -n "goPractice\|navigateTo\|practice" frontend/miniprogram/src/pages/diagnosis/index.vue
  ```

- [ ] **Step 2: 修改跳转目标**

  将：
  ```typescript
  function goPractice() {
    uni.navigateTo({ url: '/pages/practice/index' })
  }
  ```
  改为：
  ```typescript
  function goPractice() {
    uni.navigateTo({ url: '/pages/practice/adaptive' })
  }
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/miniprogram/src/pages/diagnosis/index.vue
  git commit -m "fix(miniprogram): 诊断页「智能练习」按钮跳转到 adaptive 页"
  ```

---

## Task 4：首页加"智能出题"快捷入口

**目标**：在 `index/index.vue` 的 `quick-grid` 中新增"智能出题"快捷卡，跳转到 `/pages/practice/adaptive`。

**Files:**
- Modify: `frontend/miniprogram/src/pages/index/index.vue`

- [ ] **Step 1: 定位 quick-grid**

  ```bash
  grep -n "quick-grid\|quick-card\|quick-icon" frontend/miniprogram/src/pages/index/index.vue | head -10
  ```

- [ ] **Step 2: 找到合适插入位置**

  找到"错题本"或"词力通"快捷卡前后，在 `quick-grid` 中加入：

  ```html
  <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/practice/adaptive' })">
    <text class="quick-icon">🤖</text>
    <text class="quick-label">智能出题</text>
  </view>
  ```

  建议放在"上传错题"后、"错题本"前（AI 出题与错题本属同一学习闭环）。

- [ ] **Step 3: 验证 quick-grid 布局不超出（最多 6 格）**

  ```bash
  grep -c "quick-card" frontend/miniprogram/src/pages/index/index.vue
  ```
  确认总格数 ≤ 6（超出则视觉上需要调整列数或隐藏某个低优先级入口）。

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/miniprogram/src/pages/index/index.vue
  git commit -m "feat(miniprogram): 首页快捷格新增「智能出题」入口"
  ```

---

## Task 5：归档 + 最终验证

- [ ] **Step 1: 确认所有新文件已提交**

  ```bash
  git status
  git log --oneline -6
  ```

- [ ] **Step 2: 运行已有测试确保无回归**

  ```bash
  cd backend
  python3 -c "
  from app.services.adaptive_question_service import get_adaptive_set, AdaptiveSet
  from app.api.v1.questions import router
  from app.schemas.questions import AdaptiveSetOut
  routes = [r.path for r in router.routes]
  assert '/questions/adaptive-set' in routes
  print('adaptive service + API 导入 OK')
  "
  ```

- [ ] **Step 3: 最终 commit（归档本计划）**

  ```bash
  git add docs/superpowers/specs/2026-06-07-d130-adaptive-questions-design.md \
          docs/superpowers/plans/2026-06-07-d130-adaptive-questions-plan.md
  git commit -m "docs: D-130 AI 智能出题设计文档 + 实施计划归档"
  ```

---

## 执行顺序

```
Task 1（API 测试）← 并行 → Task 2（维度 tab）
Task 3（诊断跳转）← 并行 → Task 4（首页入口）
Task 5（归档验证）← 依赖 1-4 全完成
```

Task 1-4 互相独立，可并行执行。
