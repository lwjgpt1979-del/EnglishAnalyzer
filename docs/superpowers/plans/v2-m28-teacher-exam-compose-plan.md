# V2 M28：教师出卷闭环 实施计划

**日期：** 2026-06-09
**设计文档：** `docs/superpowers/specs/v2-m28-teacher-exam-compose.md`
**测试套件目标：** 全绿（328 → ~360 passed）

---

## 执行顺序（依赖图）

```
Task 1  DB 迁移 0023（class_papers + class_paper_questions）
  ↓
Task 2  后端 service（teacher_exam_service）     ← TDD RED→GREEN
  ↓
Task 3  后端 API（teacher + student endpoints）  ← TDD RED→GREEN
  ↓
Task 4  Admin Web — ExamPapers.vue（真题上传 + 仿真题生成）
  ↓
Task 5  小程序 — 老师组卷页面
  ↓
Task 6  小程序 — 学生答题 + 成绩页
  ↓
Task 7  Build 验证 + Commit
```

---

## Task 1：DB 迁移 0023

**文件：**
- 新建 `backend/alembic/versions/0023_class_papers.py`
- 修改 `backend/app/models/d7_teacher.py`（加 ClassPaper / ClassPaperQuestion 类）

### Step 1：写迁移文件

```python
# backend/alembic/versions/0023_class_papers.py
"""class_papers + class_paper_questions

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'class_papers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('class_id', UUID(as_uuid=True), sa.ForeignKey('classes.id'), nullable=False),
        sa.Column('teacher_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('textbook_version', sa.String, nullable=True),
        sa.Column('grade', sa.String, nullable=True),
        sa.Column('semester', sa.String, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String, nullable=False, server_default='active'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_class_papers_class', 'class_papers', ['class_id'])

    op.create_table(
        'class_paper_questions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('class_paper_id', UUID(as_uuid=True), sa.ForeignKey('class_papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sim_question_id', UUID(as_uuid=True), sa.ForeignKey('simulated_questions.id'), nullable=False),
        sa.Column('order_no', sa.SmallInteger, nullable=False, server_default='1'),
    )
    op.create_index('ix_cpq_paper', 'class_paper_questions', ['class_paper_id'])
    op.create_unique_constraint('uq_cpq_paper_question', 'class_paper_questions', ['class_paper_id', 'sim_question_id'])

def downgrade():
    op.drop_table('class_paper_questions')
    op.drop_table('class_papers')
```

### Step 2：模型加类（`d7_teacher.py` 末尾）

```python
class ClassPaper(Base):
    """老师从平台仿真题库选题组成的班级试卷。"""
    __tablename__ = "class_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=False)
    teacher_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    title = mapped_column(sa.String, nullable=False)
    textbook_version = mapped_column(sa.String, nullable=True)
    grade = mapped_column(sa.String, nullable=True)
    semester = mapped_column(sa.String, nullable=True)
    description = mapped_column(sa.Text, nullable=True)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'active'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

class ClassPaperQuestion(Base):
    """班级试卷题目明细（仿真题引用）。"""
    __tablename__ = "class_paper_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("class_papers.id", ondelete="CASCADE"), nullable=False)
    sim_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("simulated_questions.id"), nullable=False)
    order_no = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("1"))
    __table_args__ = (
        sa.UniqueConstraint("class_paper_id", "sim_question_id", name="uq_cpq_paper_question"),
    )
```

### Step 3：运行迁移

```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer \
  python -m alembic upgrade head
```

---

## Task 2：后端 Service（TDD）

**文件：**
- 新建 `tests/api/test_teacher_exam.py`（先写，RED）
- 新建 `backend/app/services/teacher_exam_service.py`
- 新建 `backend/app/schemas/teacher_exam.py`

### Step 1：写测试（RED）

```python
# tests/api/test_teacher_exam.py
"""V2 M28 — 教师出卷 API 测试。"""
import uuid, pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_browse_sim_questions_requires_auth(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/teacher/sim-questions")
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_browse_sim_questions_returns_list(client: AsyncClient, teacher_token: str):
    """已认证老师 → 200 + list（允许为空）。"""
    r = await client.get(
        "/api/v1/teacher/sim-questions",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data and "total" in data

@pytest.mark.asyncio
async def test_create_class_paper(client: AsyncClient, teacher_token: str):
    """老师创建班级卷子 → 200 + paper_id。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    # 先建班级
    rc = await client.post("/api/v1/teacher/classes", json={"name": "出卷测试班"}, headers=h)
    assert rc.status_code == 200
    class_id = rc.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "期中仿真卷", "question_ids": []},
        headers=h,
    )
    assert r.status_code == 200
    paper = r.json()["data"]
    assert paper["title"] == "期中仿真卷"
    assert "paper_id" in paper

@pytest.mark.asyncio
async def test_list_class_papers(client: AsyncClient, teacher_token: str):
    """老师查班级卷子列表 → 200 + list。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    rc = await client.post("/api/v1/teacher/classes", json={"name": "列表测试班"}, headers=h)
    class_id = rc.json()["data"]["id"]
    await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "测试卷A", "question_ids": []}, headers=h,
    )
    r = await client.get(f"/api/v1/teacher/classes/{class_id}/papers", headers=h)
    assert r.status_code == 200
    papers = r.json()["data"]
    assert isinstance(papers, list)
    assert any(p["title"] == "测试卷A" for p in papers)

@pytest.mark.asyncio
async def test_delete_class_paper(client: AsyncClient, teacher_token: str):
    """老师删除自己的卷子 → 200。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    rc = await client.post("/api/v1/teacher/classes", json={"name": "删除测试班"}, headers=h)
    class_id = rc.json()["data"]["id"]
    rp = await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "待删卷", "question_ids": []}, headers=h,
    )
    paper_id = rp.json()["data"]["paper_id"]
    rd = await client.delete(f"/api/v1/teacher/papers/{paper_id}", headers=h)
    assert rd.status_code == 200

@pytest.mark.asyncio
async def test_student_can_see_class_paper(client: AsyncClient, teacher_token: str, student_token: str):
    """学生加入班级后能看到老师出的卷子。"""
    th = {"Authorization": f"Bearer {teacher_token}"}
    sh = {"Authorization": f"Bearer {student_token}"}

    # 老师建班 + 出卷
    rc = await client.post("/api/v1/teacher/classes", json={"name": "学生可见班"}, headers=th)
    class_id = rc.json()["data"]["id"]
    await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "学生可见卷", "question_ids": []}, headers=th,
    )
    # 老师生成邀请码
    ri = await client.post(f"/api/v1/teacher/classes/{class_id}/invite-code", headers=th)
    assert ri.status_code == 200
    code = ri.json()["data"]["code"]

    # 学生加入
    await client.post("/api/v1/teacher/join-class", json={"invite_code": code}, headers=sh)

    # 学生查看班级试卷
    r = await client.get(f"/api/v1/student/classes/{class_id}/papers", headers=sh)
    assert r.status_code == 200
    papers = r.json()["data"]
    assert any(p["title"] == "学生可见卷" for p in papers)
```

### Step 2：实现 `teacher_exam_service.py`

```python
# backend/app/services/teacher_exam_service.py
"""V2 M28 — 老师组卷 service。"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.models.d7_teacher import ClassPaper, ClassPaperQuestion, Class
from app.models.d12_v2_exams import SimulatedQuestion
from app.core.exceptions import AppError


async def browse_sim_questions(
    db: AsyncSession,
    *,
    textbook_version: str | None = None,
    grade: str | None = None,
    semester: str | None = None,
    kp_id: uuid.UUID | None = None,
    question_type: str | None = None,
    difficulty: int | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[SimulatedQuestion], int]:
    """浏览平台已发布仿真题（老师选题用）。"""
    base = select(SimulatedQuestion).where(SimulatedQuestion.status == "published")
    if textbook_version:
        # SimulatedQuestion 通过 knowledge_point → curriculum 关联教材；
        # MVP 简化：不做多表 join，直接返回 published 全量，前端再筛
        pass
    if kp_id:
        base = base.where(SimulatedQuestion.knowledge_point_id == kp_id)
    if question_type:
        base = base.where(SimulatedQuestion.question_type == question_type)
    if difficulty:
        base = base.where(SimulatedQuestion.difficulty == difficulty)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(SimulatedQuestion.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def create_class_paper(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    teacher_id: uuid.UUID,
    title: str,
    textbook_version: str | None = None,
    grade: str | None = None,
    semester: str | None = None,
    description: str | None = None,
    question_ids: list[uuid.UUID],
) -> ClassPaper:
    """创建班级卷子（老师组卷）。"""
    # 验证 class 属于该 teacher
    cls = (await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher_id)
    )).scalar_one_or_none()
    if cls is None:
        raise AppError(code=404, message="班级不存在或无权限")

    paper = ClassPaper(
        id=uuid.uuid4(),
        class_id=class_id,
        teacher_id=teacher_id,
        title=title,
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
        description=description,
    )
    db.add(paper)
    await db.flush()

    for idx, qid in enumerate(question_ids):
        db.add(ClassPaperQuestion(
            id=uuid.uuid4(),
            class_paper_id=paper.id,
            sim_question_id=qid,
            order_no=idx + 1,
        ))
    await db.flush()
    return paper


async def list_class_papers(
    db: AsyncSession, *, class_id: uuid.UUID
) -> list[ClassPaper]:
    rows = (await db.execute(
        select(ClassPaper)
        .where(ClassPaper.class_id == class_id, ClassPaper.status == "active")
        .order_by(ClassPaper.created_at.desc())
    )).scalars().all()
    return list(rows)


async def get_paper_with_questions(
    db: AsyncSession, *, paper_id: uuid.UUID
) -> tuple[ClassPaper, list[SimulatedQuestion]]:
    paper = (await db.execute(
        select(ClassPaper).where(ClassPaper.id == paper_id)
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在")

    q_rows = (await db.execute(
        select(SimulatedQuestion)
        .join(ClassPaperQuestion, ClassPaperQuestion.sim_question_id == SimulatedQuestion.id)
        .where(ClassPaperQuestion.class_paper_id == paper_id)
        .order_by(ClassPaperQuestion.order_no)
    )).scalars().all()
    return paper, list(q_rows)


async def delete_class_paper(
    db: AsyncSession, *, paper_id: uuid.UUID, teacher_id: uuid.UUID
) -> None:
    paper = (await db.execute(
        select(ClassPaper).where(ClassPaper.id == paper_id, ClassPaper.teacher_id == teacher_id)
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在或无权限")
    await db.execute(delete(ClassPaperQuestion).where(ClassPaperQuestion.class_paper_id == paper_id))
    await db.delete(paper)
    await db.flush()
```

### Step 3：实现 `schemas/teacher_exam.py`

```python
# backend/app/schemas/teacher_exam.py
import uuid
from pydantic import BaseModel
from datetime import datetime

class SimQuestionOut(BaseModel):
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    question_type: str
    stem: str
    options: list | None = None
    difficulty: int
    dimension: str | None = None
    model_config = {"from_attributes": True}

class SimQuestionListOut(BaseModel):
    items: list[SimQuestionOut]
    total: int

class ClassPaperCreate(BaseModel):
    title: str
    textbook_version: str | None = None
    grade: str | None = None
    semester: str | None = None
    description: str | None = None
    question_ids: list[uuid.UUID] = []

class ClassPaperOut(BaseModel):
    paper_id: uuid.UUID
    class_id: uuid.UUID
    title: str
    textbook_version: str | None = None
    grade: str | None = None
    semester: str | None = None
    description: str | None = None
    question_count: int = 0
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}

class ClassPaperDetailOut(ClassPaperOut):
    questions: list[SimQuestionOut] = []
    # 学生视角时 answer/explanation 为 None（通过 hide_answers 参数控制）
```

---

## Task 3：后端 API 路由

**文件：**
- 修改 `backend/app/api/v1/teacher.py`（加 3 个端点）
- 新建 `backend/app/api/v1/student_papers.py`（加 2 个端点）
- 修改 `backend/app/api/v1/router.py`

### 新增 teacher endpoints（teacher.py 末尾）

```python
from app.services import teacher_exam_service
from app.schemas.teacher_exam import (
    SimQuestionListOut, SimQuestionOut,
    ClassPaperCreate, ClassPaperOut, ClassPaperDetailOut
)

@router.get("/sim-questions", response_model=BaseResponse[SimQuestionListOut])
async def browse_sim_questions(
    db: DbDep, current_user: UserDep,
    kp_id: uuid.UUID | None = None,
    question_type: str | None = None,
    difficulty: int | None = None,
    skip: int = 0, limit: int = 20,
):
    """老师浏览平台仿真题库（用于组卷）。"""
    await ensure_certified(current_user)
    items, total = await teacher_exam_service.browse_sim_questions(
        db, kp_id=kp_id, question_type=question_type,
        difficulty=difficulty, skip=skip, limit=limit,
    )
    return make_ok(SimQuestionListOut(
        items=[SimQuestionOut.model_validate(q) for q in items],
        total=total,
    ))

@router.post("/classes/{class_id}/papers", response_model=BaseResponse[ClassPaperOut])
async def create_class_paper(
    class_id: uuid.UUID, body: ClassPaperCreate,
    db: DbDep, current_user: UserDep,
):
    """老师为班级出卷（从仿真题库选题）。"""
    await ensure_certified(current_user)
    paper = await teacher_exam_service.create_class_paper(
        db, class_id=class_id, teacher_id=current_user.id,
        title=body.title, textbook_version=body.textbook_version,
        grade=body.grade, semester=body.semester,
        description=body.description, question_ids=body.question_ids,
    )
    await db.commit()
    return make_ok(ClassPaperOut(
        paper_id=paper.id, class_id=paper.class_id, title=paper.title,
        textbook_version=paper.textbook_version, grade=paper.grade,
        semester=paper.semester, description=paper.description,
        question_count=len(body.question_ids), status=paper.status,
        created_at=paper.created_at,
    ))

@router.get("/classes/{class_id}/papers", response_model=BaseResponse[list[ClassPaperOut]])
async def list_class_papers(
    class_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """老师查看班级已出卷子列表。"""
    await ensure_certified(current_user)
    papers = await teacher_exam_service.list_class_papers(db, class_id=class_id)
    return make_ok([
        ClassPaperOut(
            paper_id=p.id, class_id=p.class_id, title=p.title,
            textbook_version=p.textbook_version, grade=p.grade,
            semester=p.semester, description=p.description,
            question_count=0, status=p.status, created_at=p.created_at,
        ) for p in papers
    ])

@router.delete("/papers/{paper_id}", response_model=BaseResponse[dict])
async def delete_class_paper(
    paper_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """老师删除班级卷子。"""
    await ensure_certified(current_user)
    await teacher_exam_service.delete_class_paper(
        db, paper_id=paper_id, teacher_id=current_user.id,
    )
    await db.commit()
    return make_ok({"deleted": True})
```

### 新建 student_papers.py

```python
# backend/app/api/v1/student_papers.py
"""学生查看/作答班级试卷（V2 M28）。"""
import uuid
from fastapi import APIRouter
from app.core.deps import DbDep, UserDep
from app.core.responses import BaseResponse, make_ok
from app.services import teacher_exam_service
from app.schemas.teacher_exam import ClassPaperOut, ClassPaperDetailOut, SimQuestionOut
from app.models.d7_teacher import TeacherStudent

router = APIRouter(prefix="/student", tags=["student-papers"])

@router.get("/classes/{class_id}/papers", response_model=BaseResponse[list[ClassPaperOut]])
async def list_student_class_papers(
    class_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """学生查看所在班级的试卷列表。"""
    from sqlalchemy import select
    # 验证学生在班级内
    ts = (await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.class_id == class_id,
            TeacherStudent.student_id == current_user.id,
            TeacherStudent.status == "active",
        )
    )).scalar_one_or_none()
    if ts is None:
        from app.core.exceptions import AppError
        raise AppError(code=403, message="不在该班级")

    papers = await teacher_exam_service.list_class_papers(db, class_id=class_id)
    return make_ok([
        ClassPaperOut(
            paper_id=p.id, class_id=p.class_id, title=p.title,
            textbook_version=p.textbook_version, grade=p.grade,
            semester=p.semester, description=p.description,
            question_count=0, status=p.status, created_at=p.created_at,
        ) for p in papers
    ])

@router.get("/papers/{paper_id}", response_model=BaseResponse[ClassPaperDetailOut])
async def get_student_paper_detail(
    paper_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """学生查看试卷题目（答案隐藏）。"""
    paper, questions = await teacher_exam_service.get_paper_with_questions(db, paper_id=paper_id)
    return make_ok(ClassPaperDetailOut(
        paper_id=paper.id, class_id=paper.class_id, title=paper.title,
        textbook_version=paper.textbook_version, grade=paper.grade,
        semester=paper.semester, description=paper.description,
        question_count=len(questions), status=paper.status,
        created_at=paper.created_at,
        questions=[
            SimQuestionOut(
                id=q.id, knowledge_point_id=q.knowledge_point_id,
                question_type=str(q.question_type), stem=q.stem,
                options=q.options, difficulty=q.difficulty,
                dimension=str(q.dimension) if q.dimension else None,
                # 隐藏答案（学生视角）
            ) for q in questions
        ],
    ))
```

---

## Task 4：Admin Web — ExamPapers.vue

**文件：**
- 新建 `frontend/admin/src/views/ExamPapers.vue`
- 修改 `frontend/admin/src/api/admin.ts`（加 exam paper 接口）
- 修改 `frontend/admin/src/router/index.ts`
- 修改 `frontend/admin/src/layouts/MainLayout.vue`

### admin.ts 新增接口

```typescript
export interface ExamPaperItem {
  id: string
  title: string
  textbook_version: string
  grade: string
  semester: string
  region: string | null
  status: string
  question_count: number
  sim_question_count: number
  created_at: string
}

export function listExamPapers(params?: { skip?: number; limit?: number }):
  Promise<{ items: ExamPaperItem[]; total: number }> {
  return unwrap(request.get('/admin/exam-papers', { params }))
}

export function createExamPaper(data: {
  title: string; textbook_version: string; grade: string;
  semester: string; region?: string; paper_url: string;
}): Promise<ExamPaperItem> {
  return unwrap(request.post('/admin/exam-papers', data))
}

export function generateSimQuestions(paperId: string): Promise<{ generated: number }> {
  return unwrap(request.post(`/admin/exam-papers/${paperId}/generate`))
}
```

### ExamPapers.vue 核心逻辑

- 上方：「上传真题」按钮 → 弹 Dialog（标题/教材/年级/学期/地区 + COS上传）
- 列表：id/标题/年级学期/status/题数/仿真题数/操作
- 操作列：「生成仿真题」→ confirm → POST generate → loading → 提示"已生成 N 道仿真题，请到题目审核页发布"

---

## Task 5：小程序 — 老师组卷

**文件：**
- 新建 `frontend/miniprogram/src/pages/teacher/paper-compose.vue`
- 新建 `frontend/miniprogram/src/pages/teacher/class-papers.vue`
- 修改 `frontend/miniprogram/src/api/teacher.ts`（加组卷相关接口）
- 修改 `frontend/miniprogram/src/pages.json`（注册新页）
- 修改 `frontend/miniprogram/src/pages/teacher/class-detail.vue`（加「出卷」入口）

### teacher.ts 新增

```typescript
export interface SimQuestionItem {
  id: string
  question_type: string
  stem: string
  options: string[] | null
  difficulty: number
  dimension: string | null
}

export interface ClassPaperOut {
  paper_id: string
  class_id: string
  title: string
  question_count: number
  status: string
  created_at: string
}

export function browseSimQuestions(params?: {
  kp_id?: string; question_type?: string; difficulty?: number; skip?: number; limit?: number
}): Promise<{ items: SimQuestionItem[]; total: number }> {
  return request('/api/v1/teacher/sim-questions', { data: params })
}

export function createClassPaper(classId: string, data: {
  title: string; question_ids: string[]
}): Promise<ClassPaperOut> {
  return request(`/api/v1/teacher/classes/${classId}/papers`, { method: 'POST', data })
}

export function listClassPapers(classId: string): Promise<ClassPaperOut[]> {
  return request(`/api/v1/teacher/classes/${classId}/papers`)
}

export function deleteClassPaper(paperId: string): Promise<void> {
  return request(`/api/v1/teacher/papers/${paperId}`, { method: 'DELETE' })
}
```

### class-papers.vue 核心 UI

```
页面：班级卷子列表（老师视角）
─────────────────────────────
[+ 新建卷子]        ← 跳转 paper-compose

| 期中仿真卷  | 5题 | 2026-06-09 | [删除] |
| 单元测试卷  | 3题 | 2026-06-08 | [删除] |
```

### paper-compose.vue 核心 UI

```
选题篮（右上角显示已选N题）

筛选：[题型▼] [难度▼]

─── 仿真题列表 ───────────────────
□ 1. [单选] It is __ to study... (难度★★★)
□ 2. [填空] The cat sat on __   (难度★★)
[加载更多]

─── 底部操作栏 ───────────────────
已选 3 题  [填写卷子标题]  [保存卷子]
```

---

## Task 6：小程序 — 学生查看 + 作答

**文件：**
- 新建 `frontend/miniprogram/src/api/student_papers.ts`
- 修改 `frontend/miniprogram/src/pages/teacher/class-detail.vue`（或学生的班级视图）
- 修改 `frontend/miniprogram/src/pages.json`

> **MVP 简化**：学生答题页复用 `practice/adaptive.vue` 框架，提交复用现有 `/questions/exam-attempts` 端点（已有 `submit_exam_attempts`）。

---

## Task 7：Build 验证 + Commit

```bash
# 后端测试
DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer \
  python -m pytest tests/api/test_teacher_exam.py -v

# 全套回归
DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer \
  python -m pytest tests/api/ -q --tb=short

# Admin 前端构建
cd frontend/admin && npm run build

# 小程序构建
cd frontend/miniprogram && npm run build:mp-weixin
```

**Commit message：**
```
feat(V2-M28): 教师出卷闭环（仿真题选题+组卷+班级试卷）

- migration 0023: class_papers + class_paper_questions 新表
- teacher_exam_service: 浏览仿真题/创建卷子/列表/删除
- API: GET /teacher/sim-questions, POST/GET /teacher/classes/{id}/papers
- API: GET/DELETE /teacher/papers/{id}
- API: GET /student/classes/{id}/papers, GET /student/papers/{id}
- Admin Web: ExamPapers.vue 真题上传+仿真题生成触发
- 小程序: class-papers.vue + paper-compose.vue（老师）
- 小程序: 学生班级试卷列表接入
```

---

## 风险提示

| 风险 | 缓解 |
|------|------|
| `simulated_questions` 为空（无已发布题目） | MVP 允许组空卷（`question_ids=[]`），用户体验提示"题库建设中" |
| `ensure_certified()` 拦截未认证老师 | 测试用 `teacher_token` fixture 已含认证流程 |
| `TeacherStudent` 表字段 `class_id` 可能不存在 | 需确认 TeacherStudent 模型是否有 class_id，若无则用 teacher_id+student_id 验证 |
| 答题提交与现有 exam-attempts 不同 | student_papers 的答题提交复用现有端点，结果写 sim_practice_records |
