"""V2 仿真题 + 练习 API（D-079 / M3a）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.questions import PracticeAttemptIn
from app.services import question_service

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/kp/{kp_id}/practice-questions")
async def list_practice_questions(
    kp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
):
    items = await question_service.list_questions_by_kp(db, kp_id=kp_id, limit=limit)
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
