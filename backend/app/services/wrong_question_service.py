"""错题 CRUD 业务逻辑。

所有函数使用 db.flush()，由 endpoint 层控制 commit。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.schemas.wrong_questions import WrongQuestionCreate


async def create_wrong_question(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    data: WrongQuestionCreate,
) -> WrongQuestion:
    """创建错题记录，返回已 flush 的 ORM 对象（调用方需 commit）。"""
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_url=data.source_image_url,
        question_text=data.question_text,
        student_answer=data.student_answer,
        correct_answer=data.correct_answer,
        question_type=data.question_type,
        difficulty=data.difficulty,
        tags=data.tags,
    )
    db.add(wq)
    await db.flush()
    return wq


async def get_wrong_question(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
    student_id: uuid.UUID,
) -> WrongQuestion | None:
    """按 id + student_id 查询（student_id 防止越权访问）。"""
    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.id == wq_id)
        .where(WrongQuestion.student_id == student_id)
    )
    return result.scalar_one_or_none()


def _source_filter(source: str | None):
    """来源过滤：assignment=作业（assignment://），upload=非作业。"""
    if source == "assignment":
        return [WrongQuestion.source_image_url.like("assignment://%")]
    if source == "upload":
        return [~WrongQuestion.source_image_url.like("assignment://%")]
    return []


async def list_wrong_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    source: str | None = None,
) -> tuple[list[WrongQuestion], int]:
    """分页查询当前学生的错题，按创建时间倒序，返回 (items, total)。source 可按来源过滤。"""
    conds = [WrongQuestion.student_id == student_id, *_source_filter(source)]
    count_result = await db.execute(
        select(func.count()).select_from(WrongQuestion).where(*conds)
    )
    total: int = count_result.scalar_one()

    rows = await db.execute(
        select(WrongQuestion)
        .where(*conds)
        .order_by(WrongQuestion.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(rows.scalars().all()), total


async def list_wrong_questions_by_kp(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[WrongQuestion], int]:
    """按知识点查当前学生的错题（join 关联表 wrong_question_knowledge_points），

    按创建时间倒序，返回 (items, total)。M3 关联视图用（D-093）。
    """
    from app.models.d4_knowledge import WrongQuestionKnowledgePoint

    base = (
        select(WrongQuestion)
        .join(
            WrongQuestionKnowledgePoint,
            WrongQuestionKnowledgePoint.wrong_question_id == WrongQuestion.id,
        )
        .where(
            WrongQuestion.student_id == student_id,
            WrongQuestionKnowledgePoint.knowledge_point_id == kp_id,
        )
    )
    total: int = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    rows = await db.execute(
        base.order_by(WrongQuestion.created_at.desc()).offset(skip).limit(limit)
    )
    return list(rows.scalars().all()), total


async def mark_mastered(
    db: AsyncSession,
    *,
    wq: WrongQuestion,
    is_mastered: bool,
) -> WrongQuestion:
    """切换已掌握状态；is_mastered=True 时记录 mastered_at。"""
    wq.is_mastered = is_mastered
    wq.mastered_at = datetime.now(timezone.utc) if is_mastered else None
    await db.flush()
    return wq


async def list_analyses(
    db: AsyncSession,
    *,
    wrong_question_id: uuid.UUID,
) -> list[AiAnalysis]:
    """查询某道错题的全部 AI 分析记录，按创建时间倒序。"""
    rows = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.wrong_question_id == wrong_question_id)
        .order_by(AiAnalysis.created_at.desc())
    )
    return list(rows.scalars().all())
