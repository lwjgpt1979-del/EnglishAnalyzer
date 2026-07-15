"""R3 错题中心/复习 API(KP-First,基于 wrong_record)。

学生侧:今日复习队列 + 提交复习评分(SM-2)。数据载体为 wrong_record(切换自旧 wrong_questions)。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    WrongReviewItem, WrongReviewQueueOut, WrongReviewSubmitIn, WrongReviewSubmitOut,
)
from app.services import wrong_center_service, wrong_review_service

router = APIRouter(prefix="/wrong-center", tags=["wrong-center"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/list", response_model=BaseResponse[dict])
async def list_center(
    db: DbDep, current_user: UserDep,
    kind: str | None = Query(None, description="grammar|vocab;空=全部"),
    status: str | None = Query(None, description="pending|reviewing|mastered;空=全部"),
    skip: int = 0, limit: int = 20,
):
    """「我的错题」统一列表:只读 wrong_record(题面已冗余)。语法/词汇 + 三态筛选 + 分页。"""
    items, total = await wrong_center_service.list_center(
        db, student_id=current_user.id, kind=kind, status=status, skip=skip, limit=limit)
    return make_ok({"items": items, "total": total})


@router.get("/counts", response_model=BaseResponse[dict])
async def lifecycle_counts(
    db: DbDep, current_user: UserDep,
    kind: str | None = Query(None, description="grammar|vocab;空=全部"),
):
    """状态 chip 计数(全部/待巩固/巩固中/已掌握),随 kind 变。"""
    counts = await wrong_center_service.lifecycle_counts(
        db, student_id=current_user.id, kind=kind)
    return make_ok(counts)


@router.post("/practice/{wrong_record_id}", response_model=BaseResponse[dict])
async def practice_wrong(wrong_record_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """错题「练同类仿真题」(统一入口,按 wrong_record 派发)。"""
    r = await wrong_center_service.practice_for_wrong(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id)
    await db.commit()
    kp_name = r["knowledge_point"]
    # generate 返回 AiQuestion ORM 对象,手动序列化(含 answer/explanation 供前端判分即时反馈)
    return make_ok({
        "knowledge_point": kp_name,
        "questions": [
            {
                "id": str(q.id),
                "knowledge_point_id": str(q.knowledge_point_id) if q.knowledge_point_id else None,
                "knowledge_point_name": kp_name,
                "question_type": str(q.question_type),
                "difficulty": q.difficulty,
                "stem": (q.content or {}).get("stem", ""),
                "options": (q.content or {}).get("options"),
                "answer": (q.content or {}).get("answer"),
                "explanation": (q.content or {}).get("explanation"),
            } for q in r["questions"]
        ],
    })


@router.post("/practice-result/{wrong_record_id}", response_model=BaseResponse[dict])
async def practice_result(
    wrong_record_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep,
):
    """练同类一轮做完回写成绩:记 practice_count/correct;语法据正确率推进 SM-2。
    body: {total, correct}"""
    r = await wrong_center_service.record_practice_result(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id,
        total=int(body.get("total", 0)), correct=int(body.get("correct", 0)))
    await db.commit()
    return make_ok(r)


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
