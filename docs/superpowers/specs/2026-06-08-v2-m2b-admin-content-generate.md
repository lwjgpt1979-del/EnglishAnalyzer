# V2 M2b：Admin Web 课程内容 AI 生成触发器 设计文档

**日期**：2026-06-08  
**关联**：V2 M2（课程内容 AI 生成），Admin Web M5  
**状态**：设计中

---

## 一、背景与问题

`kp-content.vue` 对学生显示"暂无内容"，因为 `knowledge_point_contents` 表几乎是空的。

| 已有 | 缺失 |
|---|---|
| `curriculum_ai_service.generate_unit()` ✅ | Admin Web 触发按钮 ❌ |
| `curriculum_service.persist_unit()` ✅ | 后端 admin 生成端点 ❌ |
| `seed_curriculum.py` CLI 脚本 ✅ | 单元内容完成度概览 ❌ |
| Admin ContentsReview（审核已有内容）✅ | 能看到哪些单元缺内容 ❌ |

---

## 二、功能设计

### 2.1 新 Admin 页面：课程单元管理（CurriculumUnits.vue）

**路由**：`/curriculum-units`

**功能**：
1. **筛选**：教材版本、年级、学期 三联下拉
2. **列表**：展示每个 unit（unit_no、unit_title、KP 数、已有内容数、内容完成率）
3. **操作**：
   - 🤖 生成内容（触发 AI，status='draft'，后续在 ContentsReview 审核）
   - 查看（跳 ContentsReview，按该 unit_id 过滤）

### 2.2 新后端端点

```
GET  /admin/curriculum/units          列出所有单元 + 内容完成度统计
POST /admin/curriculum/units/{unit_id}/generate   触发 AI 生成该单元内容
```

**`GET /admin/curriculum/units` 响应**：
```json
{
  "data": [
    {
      "unit_id": "uuid",
      "textbook_version": "译林版",
      "grade": "小学5年级",
      "semester": "上",
      "unit_no": 1,
      "unit_title": "Hello",
      "kp_count": 6,
      "content_count": 0,
      "content_rate": 0.0,
      "generating": false
    }
  ]
}
```

**`POST /admin/curriculum/units/{unit_id}/generate`**：
- 拿到 unit → 读 (textbook_version, grade, semester, unit_no)
- 调 `curriculum_ai_service.generate_unit()` → `curriculum_service.persist_unit(content_status='draft')`
- 返回 `{ "kp_count": N, "content_count": M }` 更新后的状态

### 2.3 UI 交互细节

- **生成按钮**点击 → loading 状态 → 完成后刷新该行统计
- **内容完成率**进度条（0% 红 / 1-99% 橙 / 100% 绿）
- **已有内容**：content_count = `knowledge_point_contents.status IN ('draft','reviewing','published')` 的数量 / (kp_count × 6 维度)
- dev mock 模式下生成很快（< 1s）；生产模式下 DeepSeek 可能 5-15s，需要 loading 提示

---

## 三、技术决策

### 同步生成（非后台任务）
单个单元 AI 生成约 5-15s，用同步 HTTP 请求（超时 60s）。不用 BackgroundTasks，避免前端轮询复杂度。

### content_status='draft' 默认
Admin 生成的内容先进草稿，在已有的 ContentsReview 页面审核发布，不改现有审核流程。

### 幂等
`persist_unit` 已是幂等，重复点生成只会 upsert，不会出重复数据。

---

## 四、文件清单

### 后端
| 操作 | 文件 | 内容 |
|---|---|---|
| 修改 | `backend/app/api/v1/admin.py` | 新增 `GET /curriculum/units` + `POST /curriculum/units/{id}/generate` |
| 修改 | `backend/app/services/curriculum_service.py` | 新增 `list_units_with_stats()` |

### 前端
| 操作 | 文件 | 内容 |
|---|---|---|
| 新建 | `frontend/admin/src/views/CurriculumUnits.vue` | 单元管理 + 生成按钮 |
| 修改 | `frontend/admin/src/api/admin.ts` | 新增 `listCurriculumUnits()` + `generateUnitContent()` |
| 修改 | `frontend/admin/src/types.ts` | 新增 `AdminCurriculumUnit` 类型 |
| 修改 | `frontend/admin/src/router/index.ts` | 注册 `/curriculum-units` 路由 |
| 修改 | `frontend/admin/src/layouts/MainLayout.vue` | 侧边栏加菜单项 |

### 测试
| 操作 | 文件 | 内容 |
|---|---|---|
| 新建 | `tests/api/test_admin_curriculum_generate.py` | TDD: 生成端点 + 统计端点 |

---

## 五、测试策略（TDD 先写）

- `GET /admin/curriculum/units` → 200 + list，每条有 kp_count / content_rate
- `POST /admin/curriculum/units/{unit_id}/generate` → 200 + `{ kp_count, content_count }`
- 生成后 `content_count > 0`（dev mock 确定性返回 KP + 内容）
- 无效 unit_id → 404
- 非 admin 调用 → 401

---

## 六、影响评估

- **DB**：无新迁移，只读写已有表
- **向后兼容**：ContentsReview 现有流程不变
- **生产成本**：调一次 DeepSeek 生成一个单元（8 KP × 6 维度），约 8k tokens，~¥0.04/单元
