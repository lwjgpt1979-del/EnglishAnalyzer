"""阅读表达 AI 批改 API（P2a）。独立批改端点(不走练习判分流)。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.reading_expression import ReadingExpressionGradeIn
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
