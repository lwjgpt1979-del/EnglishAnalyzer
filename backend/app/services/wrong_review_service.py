"""R3.4 错题复习(KP-First):基于 wrong_record 的 SM-2 复习队列/提交。

复用 review_service.sm2_update 纯算法;数据载体从旧 wrong_questions 切到 wrong_record。
今日队列:status=open AND next_review_at <= today。复习提交按 SM-2 调度;
quality≥4 且 review_count≥3 且 interval≥21 → 判掌握(mastery_source=review)。
"""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d16_question_domain import WrongRecord
from app.services.review_service import sm2_update

_MAX_DAILY_QUEUE = 20
_MASTER_MIN_INTERVAL = 21       # 连续高质量且间隔≥21天 → 判长期掌握


async def get_due_queue(
    db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None,
    limit: int = _MAX_DAILY_QUEUE,
) -> list[WrongRecord]:
    """今日待复习错题:open 且 next_review_at <= today,近期优先。"""
    today = today or _dt.date.today()
    return list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id,
            WrongRecord.status == "open",
            WrongRecord.next_review_at.isnot(None),
            WrongRecord.next_review_at <= today,
        ).order_by(WrongRecord.next_review_at).limit(limit)
    )).scalars().all())


async def review_queue_items(
    db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None,
    limit: int = _MAX_DAILY_QUEUE,
) -> list[dict]:
    """今日复习队列(wrong_record)映射为旧 WrongQuestionOut 形状:join uploaded_question 取内容、
    join knowledge_nodes 取 KP 名(tags)。前台读取切换直接用本数据源。"""
    from app.models.d16_question_domain import UploadedQuestion
    from app.models.d15_knowledge_graph import KnowledgeNode
    today = today or _dt.date.today()
    rows = (await db.execute(
        sa.select(WrongRecord, UploadedQuestion, KnowledgeNode.name)
        .outerjoin(UploadedQuestion, sa.and_(
            UploadedQuestion.id == WrongRecord.question_id, WrongRecord.q_scope == "uploaded"))
        .outerjoin(KnowledgeNode, KnowledgeNode.id == WrongRecord.node_id)
        .where(WrongRecord.student_id == student_id, WrongRecord.status == "open",
               WrongRecord.next_review_at.isnot(None), WrongRecord.next_review_at <= today)
        .order_by(WrongRecord.next_review_at).limit(limit)
    )).all()
    out = []
    for wr, uq, node_name in rows:
        out.append({
            "id": wr.id, "student_id": wr.student_id, "source_image_url": "",
            "question_text": (uq.stem if uq else None),
            "student_answer": (uq.student_answer if uq else None),
            "correct_answer": (uq.correct_answer if uq else None),
            "question_type": (uq.question_type if uq else None),
            "difficulty": None, "tags": ([node_name] if node_name else None),
            "is_mastered": wr.status == "mastered", "mastered_at": wr.mastered_at,
            "created_at": wr.created_at, "updated_at": wr.created_at, "ocr_status": None,
            "review_count": wr.review_count, "easiness_factor": wr.easiness_factor,
            "review_interval_days": wr.review_interval_days,
            "next_review_at": wr.next_review_at, "last_review_at": wr.last_review_at,
        })
    return out


async def review_stats(db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None) -> dict:
    """复习统计:未掌握 / 今日到期 / 新错题(未排期)。"""
    today = today or _dt.date.today()
    base = sa.select(sa.func.count()).select_from(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.status == "open")
    total = (await db.execute(base)).scalar_one()
    due = (await db.execute(base.where(WrongRecord.next_review_at.isnot(None),
                                       WrongRecord.next_review_at <= today))).scalar_one()
    new = (await db.execute(base.where(WrongRecord.next_review_at.is_(None)))).scalar_one()
    return {"total_unmastered": total, "due_today": due, "new_unscheduled": new}


async def mark_mastered(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID, is_mastered: bool,
) -> WrongRecord:
    """手动标记/取消掌握(前台直读新表):wrong_record.status = mastered|open。"""
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    if is_mastered:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "manual"
    else:
        wr.status = "open"
        wr.mastered_at = None
    await db.flush()
    return wr


async def to_wq_out_fields(db: AsyncSession, wr: WrongRecord) -> dict:
    """把 wrong_record(+ platform/uploaded 题面)映射成旧 WrongQuestionOut 字段(前台无感)。"""
    from app.models.d16_question_domain import PlatformQuestion, UploadedQuestion
    stem = correct = qtype = student_ans = None
    difficulty = None
    if wr.q_scope == "uploaded":
        uq = (await db.execute(
            sa.select(UploadedQuestion).where(UploadedQuestion.id == wr.question_id)
        )).scalar_one_or_none()
        if uq:
            stem, student_ans, correct, qtype = uq.stem, uq.student_answer, uq.correct_answer, uq.question_type
    elif wr.q_scope == "platform":   # 练习/模拟考做错的平台仿真题(KP-First 新路径)
        pq = (await db.execute(
            sa.select(PlatformQuestion).where(PlatformQuestion.id == wr.question_id)
        )).scalar_one_or_none()
        if pq:
            stem, correct, qtype, difficulty = pq.stem, pq.answer, str(pq.question_type or ""), pq.difficulty
    return {
        "id": wr.id, "student_id": wr.student_id, "source_image_url": "",
        "question_text": stem,
        "student_answer": student_ans,
        "correct_answer": correct,
        "question_type": qtype,
        "difficulty": difficulty, "tags": None,
        "is_mastered": wr.status == "mastered", "mastered_at": wr.mastered_at,
        "created_at": wr.created_at, "updated_at": wr.created_at, "ocr_status": None,
        "review_count": wr.review_count, "easiness_factor": wr.easiness_factor,
        "review_interval_days": wr.review_interval_days,
        "next_review_at": wr.next_review_at, "last_review_at": wr.last_review_at,
    }


async def submit_review(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    quality: int, today: _dt.date | None = None,
) -> WrongRecord:
    """提交一次复习评分 → SM-2 更新 next_review_at;达标则判掌握。"""
    today = today or _dt.date.today()
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在")

    r = sm2_update(
        quality=quality, review_count=wr.review_count,
        easiness_factor=Decimal(str(wr.easiness_factor)),
        review_interval_days=wr.review_interval_days, today=today,
    )
    wr.review_count = r.review_count
    wr.easiness_factor = r.easiness_factor
    wr.review_interval_days = r.review_interval_days
    wr.next_review_at = r.next_review_at
    wr.last_review_at = today

    if quality >= 4 and r.review_count >= 3 and r.review_interval_days >= _MASTER_MIN_INTERVAL:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "review"
    await db.flush()
    return wr
