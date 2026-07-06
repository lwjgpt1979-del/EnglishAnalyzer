"""书面表达(写作)练习 + AI 5 维评分 API(W2)。学生端:列练习题(带要点/结构脚手架,不下发范文)、提交作文批改。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import writing_grade_service as wgs

router = APIRouter(prefix="/writing-practice", tags=["writing-practice"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class WritingGradeByQuestionIn(BaseModel):
    question_id: uuid.UUID
    student_essay: str = Field(..., min_length=1, max_length=6000)
    full_score: int = 20


@router.get("/questions", response_model=BaseResponse[list])
async def list_writing_questions_api(
    db: DbDep, current_user: UserDep, limit: int = 10, node_id: uuid.UUID | None = None,
):
    """列可练书面表达题:下发题干 + 要点 + 结构套路(S1 脚手架),**不下发范文**(防抄)。可按 wr 节点过滤。"""
    items = await wgs.list_writing_practice_questions(db, limit=min(max(limit, 1), 50), node_id=node_id)
    return make_ok(items)


@router.post("/grade-question", response_model=BaseResponse[dict])
async def grade_writing_by_question_api(
    body: WritingGradeByQuestionIn, db: DbDep, current_user: UserDep,
):
    """按 question_id 批改作文(解析/范文服务端持有,防抄):5 维分 + 整体档 + 逐句批注 + 升格建议;
    按 wr-* 各维落 BKT(多维掌握)。返回结果标 is_ai_graded(形成性,可教师复核)。"""
    result = await wgs.grade_platform_writing_question(
        db, student_id=current_user.id, question_id=body.question_id,
        student_essay=body.student_essay, full_score=body.full_score,
    )
    await db.commit()
    return make_ok(result)
