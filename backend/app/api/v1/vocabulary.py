"""词力通词汇学习 API（P1 / D-100）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.vocabulary import DailyTaskOut, VocabAnswerIn, VocabAnswerResult
from app.services import vocabulary_service

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/daily-task", response_model=BaseResponse[DailyTaskOut])
async def daily_task(db: DbDep, current_user: UserDep):
    """今日词力通任务：到期复习词 + 新词（按会员档位上限）。"""
    await get_rls_db(db, str(current_user.id))
    task = await vocabulary_service.get_daily_task(db, student_id=current_user.id)
    return make_ok(task)


@router.post("/answer", response_model=BaseResponse[VocabAnswerResult])
async def answer(body: VocabAnswerIn, db: DbDep, current_user: UserDep):
    """提交一次作答，按 SM-2 更新记忆状态。"""
    await get_rls_db(db, str(current_user.id))
    result = await vocabulary_service.submit_answer(
        db,
        student_id=current_user.id,
        word_id=body.word_id,
        correct=body.correct,
        hesitant=body.hesitant,
    )
    await db.commit()
    return make_ok(result)
