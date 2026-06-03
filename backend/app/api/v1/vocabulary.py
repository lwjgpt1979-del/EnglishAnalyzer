"""词力通词汇学习 API（P1 / D-100）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.vocabulary import (
    DailyTaskOut,
    VocabAnswerIn,
    VocabAnswerResult,
    WrongWordItem,
    WrongWordListOut,
)
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


@router.get("/wrong-words", response_model=BaseResponse[WrongWordListOut])
async def wrong_words(db: DbDep, current_user: UserDep, skip: int = 0, limit: int = 50):
    """错词本：列出该生答错且未掌握的词（错得多的在前）。"""
    await get_rls_db(db, str(current_user.id))
    rows, total = await vocabulary_service.list_wrong_words(
        db, student_id=current_user.id, skip=skip, limit=limit,
    )

    def _pub(w) -> bool:
        return str(getattr(w, "media_status", "draft")) == "published"

    items = [
        WrongWordItem(
            word_id=w.id, word=w.word, phonetic=w.phonetic, definitions=w.definitions,
            wrong_count=lr.wrong_count, level=str(lr.level),
            image_urls=(w.image_urls if _pub(w) else None),
            en_description=(w.en_description if _pub(w) else None),
            word_audio_url=(w.word_audio_url if _pub(w) else None),
            en_desc_audio_url=(w.en_desc_audio_url if _pub(w) else None),
        )
        for lr, w in rows
    ]
    return make_ok(WrongWordListOut(total=total, items=items))
