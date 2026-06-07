# V2 M3c：旧练习路径迁移 + 学习闭环打通 设计文档

**日期**：2026-06-07  
**关联**：V2 M3a（仿真题库），D-130（智能出题），V2 M3c（本次）  
**状态**：设计中

---

## 一、背景与问题

### 两条练习路径并存

V2 上线后存在两套练习路径：

| 路径 | 入口 | 底层表 | 进诊断？ |
|---|---|---|---|
| **V1（旧）** | `practice/index.vue` | `ai_questions` + `practice_records` | ❌ |
| **V2（新）** | `kp-content.vue` → `v2-session.vue` | `simulated_questions` + `sim_practice_records` | ✅ |

V1 路径的问题：
- 做题记录不进 V2 诊断（`sim_practice_records` 才被诊断聚合）
- 用户在旧入口练习，学情数据不完整
- 两套题表并存，运营成本高

### 目标

1. **`practice/index.vue` 重写为 V2 调度页**：支持搜索知识点 → 跳 V2 session
2. **新增 `GET /curriculum/kps/search` 端点**：按关键词搜索知识点，供前端选 KP
3. **学习闭环完整**：首页 → 课程浏览 / 搜索知识点 → V2 练习 → 诊断 → 智能出题

---

## 二、功能设计

### 2.1 新 API：`GET /api/v1/curriculum/kps/search`

```
GET /api/v1/curriculum/kps/search?q=现在完成时&limit=10
Authorization: Bearer <token>

Response 200:
{
  "data": [
    {
      "id": "uuid",
      "name": "现在完成时",
      "category": "grammar",
      "description": "表示过去动作对现在的影响"
    },
    ...
  ]
}
```

**实现**：SQLAlchemy `ILIKE '%q%'` 对 `knowledge_points.name`，limit 默认 10，最大 20。  
**无鉴权要求**：知识点名称非敏感数据，可公开搜索（简化 paywall）。

### 2.2 `practice/index.vue` 重写（V2 调度页）

**新 UI 设计：**

```
┌─────────────────────────────────┐
│  🔍 搜索知识点                   │
│  [现在完成时            ] [搜索]  │
├─────────────────────────────────┤
│  📚 搜索结果                     │
│  ○ 现在完成时  grammar           │
│  ○ 现在完成式  grammar           │
├─────────────────────────────────┤
│  🤖 或者：AI 帮我选              │
│  [基于我的薄弱点智能出题]          │
└─────────────────────────────────┘
```

**行为：**
- 输入搜索词 → 调 `/curriculum/kps/search` → 展示列表
- 点击某 KP → 跳 `/pages/practice/v2-session?kp=<kpId>&dim=grammar`
- 点击"AI 帮我选" → 跳 `/pages/practice/adaptive`
- 空搜索时展示最近 5 条错题涉及的 KP（从 `wrong_questions` 联 `wrong_question_knowledge_points`）

### 2.3 学习闭环图

```
首页
  ├── 开始学习 → curriculum/units → unit-detail → kp-content
  │                                                  ├── 练习（5题）→ v2-session ─→ sim_practice_records
  │                                                  └── 模拟考（10题）→ v2-exam ─→ sim_practice_records
  │                                                                                        ↓
  ├── 智能出题 → practice/adaptive ←─────────────────────────── ai_analyses（薄弱点）
  │                                                                      ↑
  └── 学情报告 → diagnosis ←──────────────────────────── sim_practice_records + wrong_questions
  
  practice/index（重写）
    ├── 搜索 KP → v2-session
    └── 智能推荐 → adaptive
```

---

## 三、技术决策

### 不删 V1 后端 API
`/api/v1/practice/*` 后端路由保留（不做 breaking change），只停用前端调用。
原因：可能有外部集成或数据分析依赖。

### KP 搜索不加 paywall
搜索知识点名称是免费功能；只有查看知识点内容（`kp-content`）才需要学期会员。

### `practice/index.vue` 不做 tab 页
`practice/index` 在 `pages.json` 中不是 tabBar 页面，可自由改版不影响导航栏。

---

## 四、文件清单

### 后端新增/修改

| 操作 | 文件 | 内容 |
|---|---|---|
| 修改 | `backend/app/api/v1/curriculum.py` | 新增 `GET /kps/search` 端点 |
| 修改 | `backend/app/services/curriculum_service.py` | 新增 `search_kps(q, limit)` 函数 |
| 修改 | `backend/app/schemas/curriculum.py` | 新增 `KPSearchItem` schema |
| 新建 | `tests/api/test_curriculum_kp_search.py` | KP 搜索端点测试 |
| 新建 | `tests/services/test_curriculum_kp_search.py` | search_kps service 测试 |

### 前端修改

| 操作 | 文件 | 内容 |
|---|---|---|
| 新建 | `frontend/miniprogram/src/api/curriculum_kps.ts` | `searchKPs(q, limit)` |
| 修改 | `frontend/miniprogram/src/types/api.ts` | `KPSearchItem` 类型 |
| 重写 | `frontend/miniprogram/src/pages/practice/index.vue` | V2 调度页（搜索 + adaptive 入口） |

---

## 五、测试策略

### Service 测试
- `search_kps("")` → 返回最多 limit 条
- `search_kps("完成时")` → 只返回名称含"完成时"的 KP
- `search_kps("不存在")` → 返回空列表
- `search_kps("grammar", limit=3)` → 最多 3 条

### API 测试
- `GET /curriculum/kps/search?q=完成时` → 200 + 正确结构
- `GET /curriculum/kps/search`（无 q）→ 200 + 最多 10 条
- `GET /curriculum/kps/search?q=x&limit=25` → 422（limit > 20）

### 前端验证（手动）
- 输入"现在"→ 出现包含"现在"的知识点列表
- 点击知识点 → 跳转到 v2-session 页面
- 点击"AI 帮我选" → 跳转到 adaptive 页面

---

## 六、影响评估

- **DB 改动**：无（只读 knowledge_points 表）
- **API 向后兼容**：完全兼容，只新增端点
- **前端**：`practice/index.vue` 重写，不影响其他页面
- **V1 API**：后端保留，前端停止调用
