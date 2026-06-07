# D-130 AI 智能出题 + 内容完善设计文档

**日期**：2026-06-07  
**关联**：D-130（AI 智能出题），V2 M1 后续修复  
**状态**：已实现 adaptive service + API + 前端页面，待补文档 + 修 3 处 bug

---

## 一、背景与目标

### 已实现（本次补文档）
V2 M3a 建立了仿真题库，M3b 扩充了题型和模拟考。在此基础上，D-130 实现了 **AI 智能出题**：根据学生错题分析结果，自动聚合薄弱知识点，从题库取未做过的题，不足时 AI 实时补充，返回按难度排序的个性化题集。

### 待修复（3 处 bug）
1. **`kp-content.vue` 维度 tab** — 后端 migration 0022 已将维度从 4 个升为 6 个（去掉 dictation，加入 vocabulary/reading/translation），但前端 `dims` 数组未同步更新。
2. **诊断页"智能练习"按钮** — `goPractice()` 跳转到旧 `/pages/practice/index`，应改为新的 `/pages/practice/adaptive`。
3. **首页缺少"智能出题"快捷入口** — V2 首页快捷格目前无 adaptive 入口，AI 出题功能孤立。

---

## 二、D-130 架构设计

### 算法（adaptive_question_service.py）

```
ai_analyses (student_id)
    ↓ 按 knowledge_points 字段统计出现频次
top-3 薄弱 KP 名称
    ↓ 反查 knowledge_points 表
KP 对象列表
    ↓ 对每个 KP：
    1. 查 simulated_questions WHERE status='published' AND id NOT IN (已做过)
    2. 不足 2 道时调 question_ai_service.generate_questions() 补充并入库
    ↓ 合并，取前 total 道，按 difficulty ASC 排序
AdaptiveSet(questions, weak_kp_names)
```

### API

```
GET /api/v1/questions/adaptive-set?total=5
Authorization: Bearer <token>

Response 200:
{
  "data": {
    "questions": [SimQuestionOut, ...],   // 不含 answer，防作弊
    "weak_kp_names": ["现在完成时", "被动语态"]
  }
}
```

### 前端页面 (`pages/practice/adaptive.vue`)

- **Banner**：显示"针对你的薄弱点：XX、XX"
- **逐题作答**：复用 v2-session 组件模式（单选/填空/判断/写作/连线）
- **空状态**：无错题数据时提示"先做练习再来"
- **结果页**：显示正确率 + 返回按钮

---

## 三、Bug 修复设计

### Bug 1：kp-content.vue 维度 tab（4→6）

**当前（错）：**
```typescript
const dims = [
  { key: 'listening', label: '听力' },
  { key: 'dictation', label: '听写' },   // 已废弃
  { key: 'grammar', label: '语法' },
  { key: 'writing', label: '写作' },
]
```

**修复后（正）：**
```typescript
const dims = [
  { key: 'listening',    label: '听力' },
  { key: 'vocabulary',   label: '词汇' },
  { key: 'grammar',      label: '语法' },
  { key: 'reading',      label: '阅读' },
  { key: 'translation',  label: '翻译' },
  { key: 'writing',      label: '写作' },
]
```

`activeDim` 默认值从 `'grammar'` 保持不变（grammar 在新枚举中仍存在）。

### Bug 2：诊断页跳转修复

**当前（错）：**
```typescript
function goPractice() {
  uni.navigateTo({ url: '/pages/practice/index' })
}
```

**修复后（正）：**
```typescript
function goPractice() {
  uni.navigateTo({ url: '/pages/practice/adaptive' })
}
```

### Bug 3：首页加"智能出题"快捷入口

在 `index/index.vue` 的 `quick-grid` 中加一张卡：
```html
<view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/practice/adaptive' })">
  <text class="quick-icon">🤖</text>
  <text class="quick-label">智能出题</text>
</view>
```

---

## 四、测试策略（TDD）

### adaptive_question_service 测试（已写）
文件：`tests/services/test_adaptive_question_service.py`

| 测试 | 验证点 |
|---|---|
| `test_get_adaptive_set_returns_questions` | 有薄弱点时返回题目 |
| `test_get_adaptive_set_no_data_returns_empty` | 无数据时空结果不报错 |
| `test_get_adaptive_set_excludes_already_done` | 已做过的题不重复 |
| `test_get_adaptive_set_respects_total_limit` | 不超过 total 参数 |

### Bug 修复验证（新增）
文件：`tests/api/test_adaptive_api.py`

| 测试 | 验证点 |
|---|---|
| `test_adaptive_set_endpoint_returns_200` | GET /questions/adaptive-set 正常返回 |
| `test_adaptive_set_schema_no_answer_field` | 返回字段不含 answer（防作弊） |

---

## 五、文件清单

### 已实现
| 文件 | 状态 |
|---|---|
| `backend/app/services/adaptive_question_service.py` | ✅ 新建 |
| `backend/app/schemas/questions.py`（AdaptiveSetOut） | ✅ 修改 |
| `backend/app/api/v1/questions.py`（/adaptive-set） | ✅ 修改 |
| `frontend/miniprogram/src/types/api.ts`（AdaptiveSetOut） | ✅ 修改 |
| `frontend/miniprogram/src/api/questions.ts`（getAdaptiveSet） | ✅ 修改 |
| `frontend/miniprogram/src/pages/practice/adaptive.vue` | ✅ 新建 |
| `frontend/miniprogram/src/pages.json` | ✅ 修改 |
| `tests/services/test_adaptive_question_service.py` | ✅ 新建 |

### 待修复
| 文件 | 状态 |
|---|---|
| `frontend/miniprogram/src/pages/curriculum/kp-content.vue` | 🐛 dims 需更新为 6 维度 |
| `frontend/miniprogram/src/pages/diagnosis/index.vue` | 🐛 goPractice 跳转需更新 |
| `frontend/miniprogram/src/pages/index/index.vue` | 🐛 缺少智能出题快捷入口 |
| `tests/api/test_adaptive_api.py` | 📝 待新建 |

---

## 六、影响评估

- **DB 改动**：无（adaptive service 只读已有表，AI 生题走已有 persist_questions）
- **API 向后兼容**：无破坏性改动，仅新增端点
- **前端**：3 处 bug 修复均为 1-2 行改动，风险极低
