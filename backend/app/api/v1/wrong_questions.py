"""错题读取/复习 API(KP-First,统一读 wrong_record)。

拍照单题上传/OCR/AI 诊断已下线;本路由只保留基于 wrong_record 的读取、掌握标记与 SM-2 复习。
所有 endpoint 需要 Bearer JWT，并注入 RLS 变量。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.wrong_questions import (
    MarkMasteredRequest,
    RedoIn,
    RedoResultOut,
    ReviewQueueOut,
    WrongQuestionListOut,
    WrongQuestionOut,
)

router = APIRouter(prefix="/wrong-questions", tags=["wrong-questions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/by-kp/{kp_id}", response_model=BaseResponse[WrongQuestionListOut])
async def list_wrong_questions_by_kp(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """按知识 node 查当前学生的相关错题(KP-First:读 wrong_record,含平台/上传题面)。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_center_service, wrong_review_service
    rows, total = await wrong_center_service.list_by_node(
        db, student_id=current_user.id, node_id=kp_id, skip=skip, limit=limit)
    items = [WrongQuestionOut(**await wrong_review_service.to_wq_out_fields(db, wr)) for wr in rows]
    return make_ok(WrongQuestionListOut(items=items, total=total))


# ── SM-2 复习计划 ── 必须在 /{wq_id} 之前定义，否则被路由截获 ───────────────────

@router.get("/review-queue", response_model=BaseResponse[ReviewQueueOut])
async def get_review_queue(db: DbDep, current_user: UserDep):
    """今日复习队列(KP-First / wrong_record)。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_review_service
    items = await wrong_review_service.review_queue_items(db, student_id=current_user.id)
    stats = await wrong_review_service.review_stats(db, student_id=current_user.id)
    return make_ok(ReviewQueueOut(
        due_items=[WrongQuestionOut(**it) for it in items],
        stats=stats,
    ))


@router.post("/{wq_id}/error-type", response_model=BaseResponse[dict])
async def set_error_type_api(wq_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep):
    """复习时标注错因类型(记混/粗心/不会):confused|careless|unknown,落库供错因画像。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_review_service
    ok = await wrong_review_service.set_error_type(
        db, student_id=current_user.id, wrong_record_id=wq_id,
        error_type=str(body.get("error_type") or ""))
    return make_ok({"ok": ok})


@router.get("/{wq_id}", response_model=BaseResponse[WrongQuestionOut])
async def get_wrong_question(wq_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """获取单条错题详情(wrong_record,只能查自己的)。"""
    await get_rls_db(db, str(current_user.id))
    import sqlalchemy as _sa
    from app.models.d16_question_domain import WrongRecord
    from app.services import wrong_review_service
    wr = (await db.execute(_sa.select(WrongRecord).where(
        WrongRecord.id == wq_id, WrongRecord.student_id == current_user.id))).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    return make_ok(WrongQuestionOut(**await wrong_review_service.to_wq_out_fields(db, wr)))


@router.patch("/{wq_id}/mastered", response_model=BaseResponse[WrongQuestionOut])
async def mark_mastered(
    wq_id: uuid.UUID, body: MarkMasteredRequest, db: DbDep, current_user: UserDep,
):
    """标记/取消已掌握(wq_id 为 wrong_record id)。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_review_service
    wr = await wrong_review_service.mark_mastered(
        db, student_id=current_user.id, wrong_record_id=wq_id, is_mastered=body.is_mastered)
    await db.commit()
    return make_ok(WrongQuestionOut(**await wrong_review_service.to_wq_out_fields(db, wr)))


@router.post("/{wq_id}/review", response_model=BaseResponse[RedoResultOut])
async def submit_review(wq_id: uuid.UUID, body: RedoIn, db: DbDep, current_user: UserDep):
    """复习队列客观重做判分 → SM-2(答对推进、答错归零),连续达标判掌握。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_review_service
    result = await wrong_review_service.submit_review(
        db, student_id=current_user.id, wrong_record_id=wq_id, user_answer=body.user_answer,
    )
    await db.commit()
    return make_ok(RedoResultOut(**result))


@router.post("/{wq_id}/redo", response_model=BaseResponse[RedoResultOut])
async def redo_wrong(wq_id: uuid.UUID, body: RedoIn, db: DbDep, current_user: UserDep):
    """错题主动重做订正(详情入口):答对→立即掌握;答错→今日重排复习。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_review_service
    result = await wrong_review_service.redo(
        db, student_id=current_user.id, wrong_record_id=wq_id, user_answer=body.user_answer,
    )
    await db.commit()
    return make_ok(RedoResultOut(**result))
