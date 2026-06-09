# V2 M28：教师出卷闭环 设计文档

**日期：** 2026-06-09
**状态：** 设计稿，待实施

---

## 一、背景与目标

### 问题

部分机构无自有真题库，也无出题能力。平台若直接提供真题试卷，面临版权风险。

### 解决方案（版权规避过渡路径）

```
[平台运营]
  上传真题扫描件（internal only，不对外展示）
      ↓ AI 拆题
  ExamQuestion（真题原题，internal）
      ↓ AI 仿写（换词/换情境，保留考点）
  SimulatedQuestion（仿真题，status=published 后对外）
      ↓
[老师] 从平台仿真题库选题 → 组卷 → 发给班级学生
[老师] 也可上传自己的原创试卷（私有，仅本班）
```

**版权边界**：
- `exam_papers`（真题原件）+ `exam_questions`（真题原题）：**仅平台内部**，绝不对外展示
- `simulated_questions`（AI 仿写题，`status=published`）：**对外开放**，teacher / student 可见
- 老师自上传的 `exam_papers`（`source=teacher_upload`）：**私有**，仅 uploader 所属 class 可见

---

## 二、功能范围

### F1：平台运营 — 真题上传 + 仿真题生成（Admin Web）

| 功能 | 入口 | 说明 |
|------|------|------|
| 上传真题 PDF/图片 | Admin Web → 题库管理 | 填标题/教材/年级/学期；上传文件到 COS |
| 触发 OCR 拆题 | 上传后异步 | 现有 OCR pipeline；产出 `exam_questions` 行 |
| 触发仿真题生成 | Admin Web 按钮 | DeepSeek 仿写；产出 `simulated_questions`（draft） |
| 审核仿真题 | Admin Web 已有 `QuestionsReview` | approve→published；reject→retired |

> **现状**：QuestionsReview 已完成审核功能。缺：真题上传入口 + OCR拆题 + 仿真题批量生成触发器。

---

### F2：老师 — 从平台题库选题组卷（小程序）

**新流程：**
1. 老师进入某班级 → 点「出卷」
2. 筛选条件：教材版本 / 年级 / 学期 / 知识点 / 题型 / 难度
3. 浏览平台仿真题（`simulated_questions` where status=published），逐题加入「选题篮」
4. 选好后填卷子标题 → 保存为 `class_papers`
5. 卷子自动对班内所有学生可见

**班级卷子列表：**
- 老师可查看已出的卷子列表、删除
- 学生在「班级作业/试卷」tab 能看到

---

### F3：老师 — 自上传原创试卷（小程序，可选）

- 上传图片/PDF → 走 OCR pipeline
- 产出 `exam_papers`（`source=teacher_upload`，`class_id=当前班级`）
- **仅本班可见**，不进入平台公共仿真题库
- MVP 阶段可先不做 OCR 自动拆题，直接当"附件"让学生下载查看

---

### F4：学生 — 查看班级试卷（小程序）

- 已有班级视图，增加「试卷」tab
- 列出老师组的 `class_papers`
- 点进去能看到每道仿真题（答案隐藏，提交后可见）
- 成绩记录到 `sim_exam_sessions` + `sim_practice_records`（现有表）

---

## 三、数据模型

### 新增表：`class_papers`（老师组的卷子）

```sql
CREATE TABLE class_papers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  class_id      UUID NOT NULL REFERENCES classes(id),
  teacher_id    UUID NOT NULL REFERENCES users(id),
  title         VARCHAR NOT NULL,
  textbook_version VARCHAR,
  grade         VARCHAR,
  semester      semester_enum,
  description   TEXT,
  status        VARCHAR NOT NULL DEFAULT 'active',  -- active | archived
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_class_papers_class ON class_papers(class_id);
```

### 新增表：`class_paper_questions`（组卷题目明细）

```sql
CREATE TABLE class_paper_questions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  class_paper_id      UUID NOT NULL REFERENCES class_papers(id) ON DELETE CASCADE,
  sim_question_id     UUID NOT NULL REFERENCES simulated_questions(id),
  order_no            SMALLINT NOT NULL DEFAULT 1,
  UNIQUE (class_paper_id, sim_question_id)
);
CREATE INDEX ix_cpq_paper ON class_paper_questions(class_paper_id);
```

### 复用现有表

| 表 | 用途 |
|----|------|
| `simulated_questions` | 平台题库（status=published 对外） |
| `exam_papers` | 真题原件（internal）+ 老师自上传（class_id 隔离） |
| `exam_questions` | 真题原题（internal） |
| `sim_exam_sessions` | 学生做卷成绩快照 |
| `sim_practice_records` | 学生逐题作答记录 |

---

## 四、API 设计

### 4.1 Admin Web — 真题管理

```
POST   /admin/exam-papers               上传真题（title/textbook/grade/semester/paper_url）
GET    /admin/exam-papers               列出真题列表（分页）
POST   /admin/exam-papers/{id}/generate 触发仿真题生成（AI 仿写）
GET    /admin/exam-papers/{id}/questions 查真题原题列表（internal only）
```

### 4.2 Teacher — 仿真题浏览 + 组卷

```
GET  /teacher/sim-questions             浏览平台仿真题
     ?textbook_version=&grade=&semester=&kp_id=&question_type=&difficulty=&limit=20&skip=0

POST /teacher/classes/{class_id}/papers   创建组卷
     body: { title, description, question_ids: [sim_question_id, ...] }

GET  /teacher/classes/{class_id}/papers   班级卷子列表

GET  /teacher/papers/{paper_id}          卷子详情（含题目，含答案）

DELETE /teacher/papers/{paper_id}        删除卷子
```

### 4.3 Student — 查看 + 作答班级试卷

```
GET  /student/classes/{class_id}/papers  班内试卷列表（答案隐藏）

GET  /student/papers/{paper_id}          试卷详情（答案隐藏）

POST /student/papers/{paper_id}/submit   批量提交答案
     body: { answers: [{sim_question_id, user_answer}, ...] }
     → 写 sim_exam_sessions + sim_practice_records（复用现有逻辑）

GET  /student/papers/{paper_id}/result   成绩详情（提交后可见答案+解析）
```

---

## 五、Admin Web 新增页面

### 5.1 ExamPapers.vue（真题管理）

- 上传真题（表单 + COS 上传）
- 列表（title/grade/semester/status/题数/仿真题数）
- 「生成仿真题」按钮 → POST generate → loading → 完成提示

> **注意**：此页面只有 platform_admin 可见，不出现在机构后台

---

## 六、小程序新增/改动页面

| 页面 | 说明 |
|------|------|
| `teacher/paper-compose.vue` | 选题篮 + 组卷确认 |
| `teacher/class-papers.vue` | 班级卷子列表（老师视角，有删除） |
| `teacher/paper-detail.vue` | 卷子题目预览（含答案） |
| `student/class-papers.vue` | 班级试卷列表（学生视角） |
| `student/paper-exam.vue` | 答题页（复用 adaptive.vue 框架） |
| `student/paper-result.vue` | 成绩页 |

---

## 七、MVP 范围 vs 后期

### MVP（M28，本次实现）

- ✅ Admin：真题上传 + 一键生成仿真题（mock/real）
- ✅ 老师：浏览仿真题 + 选题 + 组卷 + 发班级
- ✅ 学生：查看班级试卷 + 作答 + 看成绩
- ❌ 老师自上传原创试卷（F3）：后期再做（需 OCR pipeline 扩展）
- ❌ 仿真题 AI 仿写精度优化（后期迭代）

### 后期（M29+）

- 老师上传自有试卷（F3 完整 OCR pipeline）
- 仿真题难度自动分级
- 班级成绩对比分析
- 学生订正流程

---

## 八、现有能力复用

| 现有 | 复用方式 |
|------|---------|
| COS presign upload | 真题上传走 `/upload/presign` 已有端点 |
| OCR pipeline | `ocr_service` 直接调用（暂用 mock） |
| `question_service.persist_questions` | 仿真题生成后入库 |
| `submit_exam_attempts` | 改名/复用为 paper submit |
| `sim_practice_records` 学情汇总 | 学生做卷自动入诊断 |
| Admin `QuestionsReview` | 仿真题审核已完成，无需改动 |
