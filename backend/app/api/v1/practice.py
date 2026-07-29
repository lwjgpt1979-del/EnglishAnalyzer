"""AI 练习模块 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.practice import (
    GenerateQuestionsRequest,
    PracticeQuestionOut,
    PracticeRecordOut,
    PracticeStatsOut,
    SubmitAnswerRequest,
    SubmitAnswerResult,
)
from app.services import practice_service

router = APIRouter(prefix="/practice", tags=["practice"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/generate", response_model=BaseResponse[list[PracticeQuestionOut]])
async def generate_questions(
    body: GenerateQuestionsRequest,
    db: DbDep,
    current_user: UserDep,
):
    """生成练习题（不下发答案/解析）。knowledge_point 为空则自动选最薄弱知识点。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import entitlement_service
    await entitlement_service.require_feature(db, user_id=current_user.id, key="practice.generate")
    questions = await practice_service.generate_practice_questions(
        db,
        student_id=current_user.id,
        knowledge_point=body.knowledge_point,
        count=body.count,
        difficulty=body.difficulty,
    )
    await entitlement_service.consume(db, user_id=current_user.id, key="practice.generate")
    await db.commit()

    # R8 Phase6-前置:知识点 id/名改取题上的 node_id + content 里的知识点名(生成时已写),不再查旧 knowledge_points。
    return make_ok(
        [
            PracticeQuestionOut(
                id=q.id,
                knowledge_point_id=q.node_id,
                knowledge_point_name=str(q.content.get("knowledge_point") or ""),
                question_type=str(q.question_type),
                difficulty=q.difficulty,
                stem=q.content["stem"],
                options=q.content["options"],
            )
            for q in questions
        ]
    )


@router.post("/submit", response_model=BaseResponse[SubmitAnswerResult])
async def submit_answer(
    body: SubmitAnswerRequest,
    db: DbDep,
    current_user: UserDep,
):
    """提交答案，服务端判分并返回正确答案与解析。"""
    await get_rls_db(db, str(current_user.id))
    record = await practice_service.submit_answer(
        db,
        student_id=current_user.id,
        question_id=body.question_id,
        answer=body.answer,
        time_spent_sec=body.time_spent_sec,
        source_channel=body.source_channel,
    )
    question = await practice_service.get_question(db, question_id=body.question_id)
    await db.commit()

    return make_ok(
        SubmitAnswerResult(
            record_id=record.id,
            question_id=body.question_id,
            is_correct=record.is_correct,
            correct_answer=str(question.content.get("answer", "")),
            explanation=str(question.content.get("explanation", "")),
        )
    )


@router.get("/history", response_model=BaseResponse[dict])
async def practice_history(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """分页返回练习历史。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await practice_service.get_practice_history(
        db, student_id=current_user.id, skip=skip, limit=limit
    )
    return make_ok(
        {
            "total": total,
            "items": [
                PracticeRecordOut(
                    id=r.id,
                    question_id=r.question_id,
                    is_correct=r.is_correct,
                    student_answer=str(r.student_answer.get("answer", "")),
                    practiced_at=r.practiced_at,
                    time_spent_sec=r.time_spent_sec,
                ).model_dump(mode="json")
                for r in items
            ],
        }
    )


@router.get("/stats", response_model=BaseResponse[PracticeStatsOut])
async def practice_stats(db: DbDep, current_user: UserDep):
    """返回练习统计。"""
    await get_rls_db(db, str(current_user.id))
    stats = await practice_service.get_practice_stats(db, student_id=current_user.id)
    return make_ok(PracticeStatsOut(**stats))
