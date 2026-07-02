"""阅读表达 AI 批改 API（P2a）。独立批改端点(不走练习判分流)。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.reading_expression import (
    ReadingExpressionGradeByQuestionIn, ReadingExpressionGradeIn,
)
from app.services import reading_expression_service as res

router = APIRouter(prefix="/reading-expression", tags=["reading-expression"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/grade", response_model=BaseResponse[dict])
async def grade_reading_expression_api(body: ReadingExpressionGradeIn, current_user: UserDep):
    """批改一道阅读表达简答:逐要点命中 + 内容/语言得分 + 反馈。dev-mock 离线可用。"""
    result = await res.grade_reading_expression(
        question=body.question, reference_answer=body.reference_answer,
        student_answer=body.student_answer, passage=body.passage,
        full_score=body.full_score,
    )
    return make_ok(result)


@router.get("/questions", response_model=BaseResponse[list])
async def list_reading_expression_questions_api(
    db: DbDep, current_user: UserDep, limit: int = 10, node_id: uuid.UUID | None = None,
):
    """列可练的阅读表达题(不含参考答案,防作弊);可按 KP 节点过滤。供「按题练」模式。"""
    items = await res.list_practice_questions(db, limit=min(max(limit, 1), 50), node_id=node_id)
    return make_ok(items)


@router.post("/grade-question", response_model=BaseResponse[dict])
async def grade_reading_expression_by_question_api(
    body: ReadingExpressionGradeByQuestionIn, db: DbDep, current_user: UserDep,
):
    """按 question_id 批改平台阅读表达题:参考答案服务端持有(防作弊),
    批改结果按内容命中判过/挂并落 KP 错题闭环(answer_log + student_kp)。"""
    result = await res.grade_platform_question(
        db, student_id=current_user.id, question_id=body.question_id,
        student_answer=body.student_answer, full_score=body.full_score,
    )
    await db.commit()
    return make_ok(result)
