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
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.core.exceptions import AppError


async def browse_sim_questions(
    db: AsyncSession,
    *,
    node_id: uuid.UUID | None = None,
    question_type: str | None = None,
    difficulty: int | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[PlatformQuestion], int]:
    """浏览平台已发布仿真题(老师选题用)。

    R8 Phase6a-2:题源从退役的 simulated_questions 迁到 platform_question(type='sim',已发布,
    非弃用,有答案/选项)。可选按 node_id(经 platform_question_kp)/ question_type / difficulty 筛选。
    """
    base_stmt = select(PlatformQuestion).where(
        PlatformQuestion.type == "sim",
        PlatformQuestion.status == "published",
        PlatformQuestion.deprecated_at.is_(None),
    )
    if node_id is not None:
        base_stmt = base_stmt.join(
            PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id,
        ).where(PlatformQuestionKp.node_id == node_id)
    if question_type is not None:
        base_stmt = base_stmt.where(PlatformQuestion.question_type == question_type)
    if difficulty is not None:
        base_stmt = base_stmt.where(PlatformQuestion.difficulty == difficulty)

    total: int = (await db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )).scalar_one()

    rows = (await db.execute(
        base_stmt.order_by(PlatformQuestion.created_at.desc()).offset(skip).limit(limit)
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
    - 只收录存在且已发布(platform_question type='sim' published 非弃用)的题
    - 创建 ClassPaper + ClassPaperQuestion 行（order_no 按顺序）
    """
    cls = (await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher_id)
    )).scalar_one_or_none()
    if cls is None:
        raise AppError(code=404, message="班级不存在或无权限")

    # R8 Phase6a-2:仅保留合法的 platform 仿真题(已发布、非弃用),过滤无效 id
    valid_ids = set((await db.execute(
        select(PlatformQuestion.id).where(
            PlatformQuestion.id.in_(question_ids),
            PlatformQuestion.type == "sim",
            PlatformQuestion.status == "published",
            PlatformQuestion.deprecated_at.is_(None),
        )
    )).scalars().all())

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

    order = 0
    for qid in question_ids:               # 保持老师给定顺序,仅收录合法题
        if qid not in valid_ids:
            continue
        order += 1
        db.add(ClassPaperQuestion(
            id=uuid.uuid4(),
            class_paper_id=paper.id,
            platform_question_id=qid,
            order_no=order,
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
) -> tuple[ClassPaper, list[PlatformQuestion]]:
    """返回卷子 + 有序题目列表（题源:platform_question）。"""
    paper = (await db.execute(
        select(ClassPaper).where(ClassPaper.id == paper_id)
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在")

    q_rows = (await db.execute(
        select(PlatformQuestion)
        .join(ClassPaperQuestion,
              ClassPaperQuestion.platform_question_id == PlatformQuestion.id)
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
