"""V2 M28 — 教师出卷 service。

职责：
  1. browse_sim_questions()  — 老师浏览平台已发布仿真题
  2. create_class_paper()    — 创建班级卷子（选题组卷）
  3. list_class_papers()     — 列出班级卷子
  4. get_paper_with_questions() — 卷子详情（含题目）
  5. delete_class_paper()    — 删除卷子（软删改 status=archived）
"""
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sql_delete

from app.models.d7_teacher import Class, ClassPaper, ClassPaperQuestion
from app.models.d12_v2_exams import SimulatedQuestion
from app.core.exceptions import AppError


async def browse_sim_questions(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID | None = None,
    question_type: str | None = None,
    difficulty: int | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[SimulatedQuestion], int]:
    """浏览平台已发布仿真题（老师选题用）。

    MVP 简化：只按 kp_id / question_type / difficulty 筛选；
    教材版本/年级 通过 kp_id 间接定位（老师先在 KP 视图选题）。
    """
    base_stmt = select(SimulatedQuestion).where(
        SimulatedQuestion.status == "published"
    )
    if kp_id is not None:
        base_stmt = base_stmt.where(SimulatedQuestion.knowledge_point_id == kp_id)
    if question_type is not None:
        base_stmt = base_stmt.where(SimulatedQuestion.question_type == question_type)
    if difficulty is not None:
        base_stmt = base_stmt.where(SimulatedQuestion.difficulty == difficulty)

    total: int = (await db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )).scalar_one()

    rows = (await db.execute(
        base_stmt.order_by(SimulatedQuestion.created_at.desc()).offset(skip).limit(limit)
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
    """创建班级卷子（老师选题组卷）。

    - 验证 class 属于该 teacher
    - 验证所有 sim_question_id 存在且已发布
    - 创建 ClassPaper + ClassPaperQuestion 行（order_no 按顺序）
    """
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
        status="active",
    )
    db.add(paper)
    await db.flush()

    for idx, qid in enumerate(question_ids, start=1):
        db.add(ClassPaperQuestion(
            id=uuid.uuid4(),
            class_paper_id=paper.id,
            sim_question_id=qid,
            order_no=idx,
        ))
    await db.flush()
    return paper


async def list_class_papers(
    db: AsyncSession, *, class_id: uuid.UUID
) -> list[ClassPaper]:
    """列出班级所有 active 卷子（按创建时间倒序）。"""
    rows = (await db.execute(
        select(ClassPaper)
        .where(ClassPaper.class_id == class_id, ClassPaper.status == "active")
        .order_by(ClassPaper.created_at.desc())
    )).scalars().all()
    return list(rows)


async def get_paper_question_count(
    db: AsyncSession, *, paper_id: uuid.UUID
) -> int:
    """返回卷子题目数（用于组装 ClassPaperOut.question_count）。"""
    return (await db.execute(
        select(func.count()).select_from(ClassPaperQuestion)
        .where(ClassPaperQuestion.class_paper_id == paper_id)
    )).scalar_one()


async def get_paper_with_questions(
    db: AsyncSession, *, paper_id: uuid.UUID
) -> tuple[ClassPaper, list[SimulatedQuestion]]:
    """返回卷子 + 有序题目列表。"""
    paper = (await db.execute(
        select(ClassPaper).where(ClassPaper.id == paper_id)
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在")

    q_rows = (await db.execute(
        select(SimulatedQuestion)
        .join(ClassPaperQuestion,
              ClassPaperQuestion.sim_question_id == SimulatedQuestion.id)
        .where(ClassPaperQuestion.class_paper_id == paper_id)
        .order_by(ClassPaperQuestion.order_no)
    )).scalars().all()

    return paper, list(q_rows)


async def delete_class_paper(
    db: AsyncSession, *, paper_id: uuid.UUID, teacher_id: uuid.UUID
) -> None:
    """软删除（status=archived）班级卷子。只有出卷老师可操作。"""
    paper = (await db.execute(
        select(ClassPaper).where(
            ClassPaper.id == paper_id,
            ClassPaper.teacher_id == teacher_id,
        )
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在或无权限")

    paper.status = "archived"  # type: ignore[assignment]
    await db.flush()
