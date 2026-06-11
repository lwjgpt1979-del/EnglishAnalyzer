"""ProMax 学生自助出卷（功能模块 5C，M51）。

ProMax 专属；每周最多 N 份（默认 3，自然周一 0:00 重置）。
组卷复用 adaptive_question_service.get_adaptive_set（按薄弱点）；
批改复用 question_service.submit_exam_attempts（错题统一落 wrong_questions）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d12_v2_exams import SelfExam
from app.services import (
    adaptive_question_service,
    membership_service,
    question_service,
)

WEEKLY_QUOTA = 3          # 每周自助出卷份数上限（5C，后台可配留后续）
QUESTION_COUNT = 10       # 每份题量
TIME_LIMIT_SEC = 900      # 限时 15 分钟


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=timezone.utc)


async def is_promax(db: AsyncSession, *, student_id: uuid.UUID) -> bool:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    return m is not None and str(m.tier) == "promax"


async def quota_status(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    used = (await db.execute(
        select(func.count()).select_from(SelfExam).where(
            SelfExam.student_id == student_id,
            SelfExam.created_at >= _week_start(datetime.now(timezone.utc)),
        )
    )).scalar_one()
    promax = await is_promax(db, student_id=student_id)
    return {
        "is_promax": promax,
        "used": int(used),
        "limit": WEEKLY_QUOTA,
        "remaining": max(0, WEEKLY_QUOTA - int(used)),
    }


async def create_self_exam(db: AsyncSession, *, student_id: uuid.UUID) -> SelfExam:
    if not await is_promax(db, student_id=student_id):
        raise AppError(code=403, message="自助出卷为 ProMax 会员专属功能")
    q = await quota_status(db, student_id=student_id)
    if q["remaining"] <= 0:
        raise AppError(code=429, message=f"本周自助出卷次数已用完（每周 {WEEKLY_QUOTA} 份）")

    aset = await adaptive_question_service.get_adaptive_set(
        db, student_id=student_id, total=QUESTION_COUNT
    )
    if not aset.questions:
        raise AppError(code=400, message="暂无足够可组卷的题目，请先多做练习积累薄弱点")

    snapshot = [
        {
            "id": str(x.id),
            "question_type": str(x.question_type),
            "stem": x.stem,
            "options": x.options,
            "difficulty": x.difficulty,
        }
        for x in aset.questions
    ]
    se = SelfExam(
        id=uuid.uuid4(),
        student_id=student_id,
        status="answering",
        question_ids=[str(x.id) for x in aset.questions],
        snapshot=snapshot,
        weak_kps=aset.weak_kp_names,
        time_limit_sec=TIME_LIMIT_SEC,
    )
    db.add(se)
    await db.flush()
    return se


async def get_self_exam(
    db: AsyncSession, *, exam_id: uuid.UUID, student_id: uuid.UUID
) -> SelfExam:
    se = (await db.execute(
        select(SelfExam).where(SelfExam.id == exam_id, SelfExam.student_id == student_id)
    )).scalar_one_or_none()
    if se is None:
        raise AppError(code=404, message="试卷不存在")
    return se


async def submit_self_exam(
    db: AsyncSession, *, exam_id: uuid.UUID, student_id: uuid.UUID, answers: list,
):
    se = await get_self_exam(db, exam_id=exam_id, student_id=student_id)
    if str(se.status) == "done":
        raise AppError(code=400, message="该试卷已提交")

    result = await question_service.submit_exam_attempts(
        db, user_id=student_id, answers=answers
    )
    se.status = "done"  # type: ignore[assignment]
    se.total = result.total  # type: ignore[assignment]
    se.correct_count = result.correct_count  # type: ignore[assignment]
    se.accuracy = (result.correct_count / result.total) if result.total else 0.0  # type: ignore[assignment]
    se.submitted_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    await db.flush()
    return se, result


async def list_history(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50
) -> list[SelfExam]:
    return list((await db.execute(
        select(SelfExam)
        .where(SelfExam.student_id == student_id)
        .order_by(SelfExam.created_at.desc())
        .limit(limit)
    )).scalars().all())
