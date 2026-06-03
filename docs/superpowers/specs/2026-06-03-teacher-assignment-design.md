# 老师出卷下发闭环 设计（D-113，Module 5B + 5B-S）

**日期：** 2026-06-03
**归属：** P1 老师端。班级管理（D-069）已就绪；本切片补 assignment 出卷→下发→作答→批改闭环。

## 背景与目标

老师在已建班级里**手动出卷**（题目存 questions JSONB）→ 发布下发（站内通知班级学生）→ 学生接收作答提交 → 老师手动打总分 → 学生看分。表 `assignments`/`assignment_submissions` 就绪（status: draft/published/closed）。

## 关键决策（已确认）

- 出题：**仅手动**（AI 智能选题/薄弱点组卷留后续）。
- 批改：**老师手动打总分**（score；无评语列→不做评语；自动判分留后续）。
- 学生入口：**首页宫格「老师任务」**。
- 学生接收全档位可用；老师端需 certified（`_require_certified_teacher`）。
- **零迁移**（表就绪）、**无花钱**（无 LLM）。

## 数据模型（就绪，零迁移）

- `assignments`: id, teacher_id, class_id, title, questions(JSONB), due_at, status(draft/published/closed), published_at, created_at, updated_at。
- `assignment_submissions`: id, assignment_id, student_id, answers(JSONB), score(Numeric5,2 nullable), submitted_at, updated_at。每生每作业唯一。

`questions` JSONB 约定：`[{stem, type?, options?, answer?}]`（手动录入；type/options/answer 可空）。
`answers` JSONB 约定：`[{index, answer}]` 或 `{题号: 答案}`，MVP 透传存储（前端结构化、后端不解析判分）。

## 架构与组件

### 后端 `assignment_service.py`（新建）

**老师端：**
```python
async def create_assignment(db, *, teacher_id, class_id, title, questions, due_at=None) -> Assignment:
    # class_service._get_owned_class 校验班级归属 → status=draft
async def publish_assignment(db, *, teacher_id, assignment_id) -> Assignment:
    # 取本人 draft/published 作业；draft→published + published_at=now()
    # emit 站内通知给班级每个学生（notification_service.emit type_="assignment"）
async def close_assignment(db, *, teacher_id, assignment_id) -> Assignment:
    # published→closed
async def list_teacher_assignments(db, *, teacher_id, class_id=None) -> list[Assignment]
async def get_assignment_for_teacher(db, *, teacher_id, assignment_id) -> tuple[Assignment, list[AssignmentSubmission]]:
    # 校验归属 → 作业 + 提交列表
async def grade_submission(db, *, teacher_id, submission_id, score) -> AssignmentSubmission:
    # 校验该 submission 所属作业归本老师 → 写 score
```
- 归属/状态校验失败 → `AppError(404/403/400)`。
- `_get_owned_assignment(db, teacher_id, assignment_id)` 私有 helper（select where id & teacher_id，None→404）。

**学生端：**
```python
async def list_received(db, *, student_id) -> list[tuple[Assignment, AssignmentSubmission | None]]:
    # 学生所在班级（ClassStudent）的 published 作业 + 我的提交（可空）
async def get_for_student(db, *, student_id, assignment_id) -> tuple[Assignment, AssignmentSubmission | None]:
    # 校验：作业 published 且学生在该 class（ClassStudent）→ 否则 403/404
async def submit_assignment(db, *, student_id, assignment_id, answers) -> AssignmentSubmission:
    # 校验在班级 + published + （due_at 为空或未过）→ upsert submission（已存在则更新 answers + submitted_at）
```
- 截止校验：`due_at` 非空且 `now > due_at` → `AppError(400, "作业已截止")`。

**通知**：`publish_assignment` 内查班级学生（`ClassStudent.class_id==`）→ 逐个 `notification_service.emit(db, user_id=sid, type_="assignment", title="老师布置了新作业", content=f"《{title}》，请尽快完成。", meta={"assignment_id": str(aid)})`。

### 后端 schemas（`schemas/assignment.py` 新建）
```python
class AssignmentQuestion(BaseModel):
    stem: str
    type: str | None = None
    options: list[str] | None = None
    answer: str | None = None

class AssignmentCreate(BaseModel):
    class_id: uuid.UUID
    title: str = Field(..., min_length=1)
    questions: list[AssignmentQuestion]
    due_at: str | None = None  # ISO

class AssignmentOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str
    questions: list[AssignmentQuestion]
    due_at: str | None = None
    status: str
    published_at: str | None = None
    created_at: str

class AssignmentListItem(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str
    status: str
    due_at: str | None = None
    submission_count: int = 0   # 老师端列表用；学生端复用时可忽略

class SubmissionItem(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    answers: list | dict
    score: float | None = None
    submitted_at: str

class TeacherAssignmentDetail(BaseModel):
    assignment: AssignmentOut
    submissions: list[SubmissionItem]

class StudentAssignmentItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    due_at: str | None = None
    submitted: bool
    score: float | None = None

class StudentAssignmentDetail(BaseModel):
    assignment: AssignmentOut
    submitted: bool
    answers: list | dict | None = None
    score: float | None = None

class SubmitIn(BaseModel):
    answers: list | dict

class GradeIn(BaseModel):
    score: float = Field(..., ge=0)
```

### 后端 API

**老师端（`api/v1/teacher.py` 追加，沿用 `_require_certified_teacher`）：**
- `POST /teacher/assignments`（create，body AssignmentCreate）
- `POST /teacher/assignments/{id}/publish`
- `POST /teacher/assignments/{id}/close`
- `GET /teacher/assignments?class_id=`（list，AssignmentListItem 带 submission_count）
- `GET /teacher/assignments/{id}`（TeacherAssignmentDetail）
- `POST /teacher/submissions/{sid}/grade`（GradeIn）

**学生端（`api/v1/assignments.py` 新建，prefix `/assignments`，注册 router）：**
- `GET /assignments`（list_received → StudentAssignmentItem[]）
- `GET /assignments/{id}`（StudentAssignmentDetail）
- `POST /assignments/{id}/submit`（SubmitIn）

> due_at 解析：API 收 ISO str → `datetime.fromisoformat`；service 比较用 aware datetime。

### 前端

**老师端：**
- `pages/teacher/assignments.vue`：某班级的作业列表（从 class-detail 进，带 classId）+ 「出卷」表单（title + 动态增删题目 stem/options/answer + due）→ create → 列表；每项可发布/关闭/查看。
- `pages/teacher/assignment-detail.vue`：题目 + 提交列表（每生答案 + 打分输入 + 提交批改）。
- 入口：`class-detail.vue` 加「作业/出卷」按钮 → `assignments?classId=`。
- pages.json 注册；`api/assignments.ts`（teacher 部分）+ types。

**学生端：**
- `pages/assignments/index.vue`：收到的作业列表（标题/状态/截止/是否已交/分数）。
- `pages/assignments/detail.vue`：题目 + 作答（每题输入）+ 提交；已交则展示答案 + 分数。
- 首页宫格「📋 老师任务」→ `pages/assignments/index`。
- pages.json 注册；`api/assignments.ts`（student 部分）+ types。

## 测试（TDD）

**service（tests/services/test_assignment_service.py 新）**
1. create（draft）+ 非本人班级 → 403。
2. publish（draft→published+published_at）+ 班级学生收到站内通知（查 Notification type=assignment）。
3. close（published→closed）。
4. 学生 list_received：本班 published 可见、未发布不可见、非本班不可见。
5. 学生 submit：成功 upsert；重复提交更新同一行；非本班 → 403；已截止 → 400。
6. grade_submission：老师给分写入；非本老师作业 → 403。

**API（tests/api/test_assignment.py 新）**
7. 全链路：老师建→发布→学生收到列表→作答提交→老师批改→学生看分。
8. 鉴权：未登录 401；非 certified 老师出卷 403；学生看非本班作业 403/404。

## 影响范围

- `backend/app/services/assignment_service.py`（新）
- `backend/app/schemas/assignment.py`（新）
- `backend/app/api/v1/teacher.py`（+assignment 端点）、`backend/app/api/v1/assignments.py`（新，学生端）、`router.py`（注册）
- `tests/services/test_assignment_service.py`、`tests/api/test_assignment.py`（新）
- 前端老师 `pages/teacher/assignments.vue`/`assignment-detail.vue` + class-detail 入口；学生 `pages/assignments/index.vue`/`detail.vue` + 首页入口；`api/assignments.ts`、types、pages.json
- **零迁移、无花钱**（复用通知）。

## 任务拆分（6 任务）

1. assignment_service 老师端（create/publish/close/list/detail/grade）+ service 测试
2. assignment_service 学生端（list_received/get_for_student/submit）+ service 测试
3. schemas + API（老师端 teacher.py + 学生端 assignments.py + router）+ API 全链路测试
4. 前端老师端（assignments 列表/出卷 + detail/批改 + class-detail 入口）
5. 前端学生端（作业列表/作答 + 首页「老师任务」入口）
6. 全量回归 + 归档 D-113

## 不做（后续）

- AI 智能选题 / 薄弱点组卷 / 错题库引用组卷
- 自动判分（题目带答案逐题判）
- 批改评语（无字段，需迁移）
- 作业统计大盘 / 逾期提醒推送
- 机构维度作业

## 相关

D-069（班级管理）、D-074（通知）；需求 Module 5B、5B-S。
