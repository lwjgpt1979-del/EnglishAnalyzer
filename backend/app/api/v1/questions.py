"""V2 仿真题 + 练习 API（D-079 / M3a）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.questions import AdaptiveSetOut, ExamAttemptIn, PracticeAttemptIn, SimQuestionOut
from app.services import adaptive_question_service, question_service

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/kp/{kp_id}/practice-questions")
async def list_practice_questions(
    kp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
    dimension: str | None = Query(None, description="按维度过滤：listening/dictation/grammar/writing"),
):
    items = await question_service.list_questions_by_kp(
        db, kp_id=kp_id, dimension=dimension, limit=limit,
    )
    return make_ok([i.model_dump(mode="json") for i in items])


@router.post("/practice-attempts")
async def submit_practice_attempt(
    body: PracticeAttemptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await question_service.submit_attempt(
        db,
        user_id=current_user.id,
        question_id=body.question_id,
        user_answer=body.user_answer,
    )
    await db.commit()  # 错题落库要 commit
    return make_ok(result.model_dump(mode="json"))


@router.post("/exam-attempts")
async def submit_exam_attempts(
    body: ExamAttemptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模拟考批量提交：一次判 N 题，错题统一落库，返回总分 + 每题结果。"""
    result = await question_service.submit_exam_attempts(
        db,
        user_id=current_user.id,
        answers=body.items,
    )
    await db.commit()  # 错题落库要 commit
    return make_ok(result.model_dump(mode="json"))


@router.get("/kp-accuracy")
async def get_kp_accuracy(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """学情：按知识点聚合练习正确率，弱项（正确率低）在前。"""
    result = await question_service.get_kp_accuracy(db, user_id=current_user.id)
    return make_ok(result.model_dump(mode="json"))


@router.get("/exam-history")
async def get_exam_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
):
    """模拟考成绩历史，最新在前。"""
    result = await question_service.get_exam_history(
        db, user_id=current_user.id, limit=limit,
    )
    return make_ok(result.model_dump(mode="json"))


@router.get("/adaptive-set", response_model=None)
async def get_adaptive_set(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    total: int = Query(5, ge=1, le=10, description="本次出题总数"),
):
    """智能出题：根据学生薄弱知识点自动组卷，返回未做过的推荐题目。"""
    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=current_user.id, total=total
    )
    await db.commit()
    questions_out = [
        SimQuestionOut(
            id=q.id,
            question_type=q.question_type,
            stem=q.stem,
            options=q.options,
            difficulty=q.difficulty,
        )
        for q in result.questions
    ]
    return make_ok(
        AdaptiveSetOut(questions=questions_out, weak_kp_names=result.weak_kp_names).model_dump(mode="json")
    )


@router.get("/exam-rank")
async def get_exam_rank(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """学生端：我在所属班级的模拟考排名（百分位，不显示他人姓名）。"""
    result = await question_service.get_exam_rank(db, user_id=current_user.id)
    return make_ok(result.model_dump(mode="json"))
