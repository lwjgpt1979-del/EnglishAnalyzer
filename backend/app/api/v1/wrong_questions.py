"""错题 CRUD API。

所有 endpoint 需要 Bearer JWT，并注入 RLS 变量。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.wrong_questions import (
    AiAnalysisOut,
    MarkMasteredRequest,
    ReviewQueueOut,
    SubmitReviewIn,
    WrongQuestionCreate,
    WrongQuestionListOut,
    WrongQuestionOut,
)
from app.services import review_service, wrong_question_service
from pydantic import BaseModel as _BaseModel


class AutoTagOut(_BaseModel):
    processed: int

router = APIRouter(prefix="/wrong-questions", tags=["wrong-questions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/", response_model=BaseResponse[WrongQuestionOut])
async def create_wrong_question(
    body: WrongQuestionCreate,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """提交新错题（MVP：前端先上传图片到 OSS，再传 URL）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.create_wrong_question(
        db, student_id=current_user.id, data=body
    )
    # 初始化 ocr_status = pending 并触发后台 OCR
    wq.ocr_status = "pending"  # type: ignore[assignment]
    await db.commit()
    await db.refresh(wq)

    from app.api.v1.ocr import _run_ocr_pipeline
    background_tasks.add_task(_run_ocr_pipeline, wq.id)

    return make_ok(WrongQuestionOut.model_validate(wq))


@router.get("/", response_model=BaseResponse[WrongQuestionListOut])
async def list_wrong_questions(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    source: str | None = Query(None, description="来源筛选：assignment/upload，空=全部"),
    tag: str | None = Query(None, description="知识点标签筛选，空=全部（M38）"),
):
    """获取当前学生的错题列表（分页，按创建时间倒序，可按来源/标签筛选）。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await wrong_question_service.list_wrong_questions(
        db, student_id=current_user.id, skip=skip, limit=limit, source=source, tag=tag
    )
    return make_ok(
        WrongQuestionListOut(
            items=[WrongQuestionOut.model_validate(wq) for wq in items],
            total=total,
        )
    )


@router.get("/by-kp/{kp_id}", response_model=BaseResponse[WrongQuestionListOut])
async def list_wrong_questions_by_kp(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """按知识点查当前学生的相关错题（M3 关联视图，D-093）。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await wrong_question_service.list_wrong_questions_by_kp(
        db, student_id=current_user.id, kp_id=kp_id, skip=skip, limit=limit
    )
    return make_ok(
        WrongQuestionListOut(
            items=[WrongQuestionOut.model_validate(wq) for wq in items],
            total=total,
        )
    )


# ── SM-2 复习计划（M36）— 必须在 /{wq_id} 之前定义，否则 FastAPI 路由被截获 ───────

@router.get("/review-queue", response_model=BaseResponse[ReviewQueueOut])
async def get_review_queue(db: DbDep, current_user: UserDep):
    """今日复习队列：到期待复习 + 新错题初始化调度。"""
    await get_rls_db(db, str(current_user.id))
    # 先初始化新错题（安排今日复习）
    await review_service.get_new_queue(db, student_id=current_user.id)
    await db.commit()
    # 再取今日队列
    due_items = await review_service.get_today_review_queue(db, student_id=current_user.id)
    stats = await review_service.get_review_stats(db, student_id=current_user.id)
    return make_ok(ReviewQueueOut(
        due_items=[WrongQuestionOut.model_validate(wq) for wq in due_items],
        stats=stats,
    ))


@router.post("/auto-tag", response_model=BaseResponse[AutoTagOut])
async def auto_tag_wrong_questions(db: DbDep, current_user: UserDep):
    """批量补标：将有 AI 分析但缺 tags 的错题自动补全知识点标签（M38）。"""
    await get_rls_db(db, str(current_user.id))
    processed = await wrong_question_service.auto_tag_all(db, student_id=current_user.id)
    await db.commit()
    return make_ok(AutoTagOut(processed=processed))


@router.get("/{wq_id}", response_model=BaseResponse[WrongQuestionOut])
async def get_wrong_question(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """获取单条错题详情（只能查自己的）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    return make_ok(WrongQuestionOut.model_validate(wq))


@router.patch("/{wq_id}/mastered", response_model=BaseResponse[WrongQuestionOut])
async def mark_mastered(
    wq_id: uuid.UUID,
    body: MarkMasteredRequest,
    db: DbDep,
    current_user: UserDep,
):
    """标记/取消已掌握。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    wq = await wrong_question_service.mark_mastered(db, wq=wq, is_mastered=body.is_mastered)
    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))


@router.post("/{wq_id}/analyze", response_model=BaseResponse[AiAnalysisOut])
async def analyze_wrong_question(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """触发 AI 分析（同步，约 3-8 秒）。每次调用生成新的分析记录。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    # OCR 尚未完成时拒绝触发 AI 分析
    if wq.ocr_status not in ("completed", None):
        raise AppError(
            code=400,
            message=f"OCR 识别尚未完成（当前状态：{wq.ocr_status}），请稍后再试",
        )

    from app.services import ai_service  # 延迟导入，避免启动时加载 openai

    analysis = await ai_service.analyze_wrong_question(db, wq=wq, student_id=current_user.id)
    await db.commit()
    await db.refresh(analysis)
    return make_ok(AiAnalysisOut.model_validate(analysis))


@router.get("/{wq_id}/analyses", response_model=BaseResponse[list[AiAnalysisOut]])
async def list_analyses(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查询某道错题的全部 AI 分析历史。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    analyses = await wrong_question_service.list_analyses(db, wrong_question_id=wq_id)
    return make_ok([AiAnalysisOut.model_validate(a) for a in analyses])


@router.post("/{wq_id}/review", response_model=BaseResponse[WrongQuestionOut])
async def submit_review(
    wq_id: uuid.UUID,
    body: SubmitReviewIn,
    db: DbDep,
    current_user: UserDep,
):
    """提交复习质量（0-5），更新 SM-2 调度。"""
    await get_rls_db(db, str(current_user.id))
    wq = await review_service.submit_review(
        db, wq_id=wq_id, student_id=current_user.id, quality=body.quality,
    )
    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))
