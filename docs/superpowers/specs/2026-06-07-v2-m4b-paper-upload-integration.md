# V2 M4b：整卷上传全链路打通 设计文档

**日期**：2026-06-07  
**关联**：V2 M4（整卷上传 OCR 拆题），V2 M3c（练习路径迁移）  
**状态**：设计中

---

## 一、背景与问题

### M4 实现状况

V2 M4 已完成后端和前端页面，但存在"孤立"问题：

| 层次 | 状态 | 问题 |
|---|---|---|
| 后端 API | ✅ `POST /user-papers`、`GET /user-papers/{id}` | 完整，背景 OCR 管线可运行 |
| 前端页面 | ✅ `user-papers/upload.vue`、`list.vue`、`detail.vue` | 页面完整 |
| 首页入口 | ❌ 无 | 用户无法发现整卷功能 |
| 错题系统联动 | ❌ 无 | `user_paper_questions.is_wrong=True` 不出现在错题本 |
| 诊断联动 | ❌ 无 | 整卷答题不计入 V2 诊断 |

### 目标

1. **首页双入口**：区分"上传错题（单题）"和"上传整卷"
2. **错题本联动**：`user_paper_questions.is_wrong=True` 在错题本出现（来源标签"整卷"）
3. **诊断联动**：整卷错题 → 错误知识点 → 薄弱点 → 诊断报告（通过 `wrong_question_knowledge_points` 桥接）

---

## 二、功能设计

### 2.1 首页改版

**当前 8 格快捷宫格：**
```
🤖 智能出题 | 📷 上传错题 | 📚 我的错题 | 📊 学情报告
🔤 词力通   | ✍️ 作文精修 | 📋 老师任务 | 👤 个人中心
```

**新 8 格（替换"上传错题"为两个入口，压缩一格）：**
```
🤖 智能出题 | 📷 单题上传 | 📄 上传整卷 | 📚 我的错题
📊 学情报告 | 🔤 词力通   | ✍️ 作文精修 | 📋 老师任务
```

- `📷 单题上传` → `/pages/upload/index`（保留 V1 流程）
- `📄 上传整卷` → `/pages/user-papers/upload`（V2 整卷）
- 去掉"👤 个人中心"快捷卡（可从 TabBar 底部进入）

### 2.2 错题本联动

**目标**：`user_paper_questions.is_wrong=True` 的题在"错题本"可见，来源=`paper`。

**方案**：新增 API `GET /api/v1/wrong-questions?source=paper` 能同时返回 V1 + paper 来源题目。

**实现思路（轻量桥接，不改表结构）**：
- 后端 `wrong_question_service.list_wrong_questions()` 新增 source 参数 `paper`
- 当 `source=paper` 时，查询 `user_paper_questions` where `is_wrong=True`，映射为 `WrongQuestionOut` 格式
- 当 `source=all` 时，合并 V1 + paper 结果（union 或内存合并）
- 前端错题本 source tabs 增加"整卷"选项

**WrongQuestionOut 映射**（user_paper_questions → WrongQuestionOut）：
```
id            → id
question_text → stem (user_paper_questions.stem)
is_mastered   → False (整卷错题暂不支持掌握标记)
source_label  → "整卷"
question_type → user_paper_questions.question_type
image_url     → None（已做 OCR，不需要图）
```

### 2.3 诊断联动（轻量版）

整卷错题已有 `user_paper_question_knowledge_points` 关联表，可用于诊断。

**轻量实现**：在 `diagnosis_service._aggregate_structured_dimensions()` 中额外查询：
```sql
SELECT upqkp.knowledge_point_id, False as is_correct
FROM user_paper_question_knowledge_points upqkp
JOIN user_paper_questions upq ON upq.id = upqkp.user_paper_question_id
WHERE upq.student_id = :student_id AND upq.is_wrong = True
```
将整卷错题 KP 计入 `kp_agg`（is_correct=False），使弱项检测更全面。

---

## 三、技术决策

### 不改 wrong_questions 表结构
V1 的 `wrong_questions` 表已有 `source` 字段（'upload' / 'assignment'）。整卷题保持在 `user_paper_questions` 独立表，通过后端 service 层联合查询，**不做表迁移**。

### source=paper 时返回 UserPaperQuestion 适配体
只需在 service 层建 adapter function，把 `UserPaperQuestion` 转成 `WrongQuestionOut`。不需要 Pydantic 继承改动。

### 诊断联动只计 is_wrong=True 且有 KP 关联的题
`user_paper_question_knowledge_points` 只有在 paper_split_service 正确识别知识点时才有数据（dev mock 有默认知识点关联），生产环境依赖 AI 归类质量。

---

## 四、文件清单

### 后端修改

| 操作 | 文件 | 内容 |
|---|---|---|
| 修改 | `backend/app/services/wrong_question_service.py` | `list_wrong_questions()` 支持 `source='paper'`，新增 adapter |
| 修改 | `backend/app/services/diagnosis_service.py` | `_aggregate_structured_dimensions()` 增加整卷错题 KP |
| 修改 | `backend/app/schemas/wrong_questions.py` | 确认 `WrongQuestionOut` 有 `source_label` 字段（或新增） |

### 前端修改

| 操作 | 文件 | 内容 |
|---|---|---|
| 修改 | `frontend/miniprogram/src/pages/index/index.vue` | 首页快捷宫格加"上传整卷"，移除"个人中心"快捷卡 |
| 修改 | `frontend/miniprogram/src/pages/wrong-questions/list.vue` | source tabs 增加"整卷" |
| 修改 | `frontend/miniprogram/src/api/wrongQuestions.ts` | `listWrongQuestions()` 支持 source='paper' |

### 测试

| 操作 | 文件 | 内容 |
|---|---|---|
| 新建 | `tests/services/test_wrong_question_paper_source.py` | TDD: paper source 列表正确返回 |
| 新建 | `tests/services/test_diagnosis_paper_integration.py` | TDD: 整卷错题 KP 计入诊断 |

---

## 五、测试策略

### Service 测试（TDD 先写）

**wrong_question_service:**
- `list_wrong_questions(source='paper')` → 返回 `is_wrong=True` 的 UserPaperQuestion 适配体
- `list_wrong_questions(source='all')` → 合并 V1 + paper 结果
- `list_wrong_questions(source='upload')` → 只返回 V1 upload 来源（不变）
- paper 适配体有正确字段：`id, question_text, is_mastered=False, source_label='整卷'`

**diagnosis_service:**
- 有整卷错题（is_wrong=True + KP 关联）→ `kp_dimension` 包含该 KP，accuracy < 1.0
- 无整卷错题 → `kp_dimension` 只来自 sim_practice_records（不变）

### 前端验证（手动）
- 首页"📄 上传整卷"快捷卡存在，点击进入 user-papers/upload
- 错题本"整卷" tab 存在，显示整卷错题

---

## 六、影响评估

- **DB 改动**：无（只读新表，不改表结构）
- **API 向后兼容**：完全兼容，`source` 参数可选，默认行为不变
- **前端**：首页宫格微调，错题本增加一个 tab
- **诊断准确性**：整卷错题数据加入后，薄弱点识别更准确
