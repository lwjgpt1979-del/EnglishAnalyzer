"""R3 错题中心/复习 API(KP-First,基于 wrong_record)。

学生侧:今日复习队列 + 提交复习评分(SM-2)。数据载体为 wrong_record(切换自旧 wrong_questions)。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    WrongReviewItem, WrongReviewQueueOut, WrongReviewSubmitIn, WrongReviewSubmitOut,
)
from app.services import wrong_review_service

router = APIRouter(prefix="/wrong-center", tags=["wrong-center"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/review-queue", response_model=BaseResponse[WrongReviewQueueOut])
async def review_queue(db: DbDep, current_user: UserDep):
    """今日待复习错题队列(KP-First / wrong_record)。"""
    rows = await wrong_review_service.get_due_queue(db, student_id=current_user.id)
    items = [WrongReviewItem(
        id=r.id, q_scope=r.q_scope, question_id=r.question_id, node_id=r.node_id,
        review_count=r.review_count, next_review_at=r.next_review_at,
    ) for r in rows]
    return make_ok(WrongReviewQueueOut(due_count=len(items), items=items))


@router.post("/review", response_model=BaseResponse[WrongReviewSubmitOut])
async def submit_review(body: WrongReviewSubmitIn, db: DbDep, current_user: UserDep):
    """提交复习评分 → SM-2 调度;达标判掌握。"""
    wr = await wrong_review_service.submit_review(
        db, student_id=current_user.id, wrong_record_id=body.wrong_record_id, quality=body.quality,
    )
    await db.commit()
    return make_ok(WrongReviewSubmitOut(
        status=wr.status, review_count=wr.review_count, next_review_at=wr.next_review_at,
    ))
