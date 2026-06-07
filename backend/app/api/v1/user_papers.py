"""整卷上传 OCR 拆题 API（D-089 / M4）。

POST /user-papers          建卷 + 触发后台 OCR 拆题管线
GET  /user-papers          列出本人整卷
GET  /user-papers/{id}     整卷详情（含拆出的题目）
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.user_papers import UserPaperCreate, UserPaperListOut
from app.services import user_paper_service

router = APIRouter(prefix="/user-papers", tags=["user-papers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("")
async def create_user_paper(
    body: UserPaperCreate,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """建卷并异步触发 OCR 拆题。"""
    paper = await user_paper_service.create_paper(
        db,
        student_id=current_user.id,
        source_image_urls=body.source_image_urls,
        title=body.title,
    )
    await db.commit()

    background_tasks.add_task(user_paper_service.run_paper_pipeline, paper.id)

    return make_ok(
        {
            "id": str(paper.id),
            "title": paper.title,
            "ocr_status": paper.ocr_status,
        }
    )


@router.get("")
async def list_user_papers(
    db: DbDep,
    current_user: UserDep,
):
    """列出本人整卷。"""
    items = await user_paper_service.list_papers(db, student_id=current_user.id)
    out = UserPaperListOut(items=items, total=len(items))
    return make_ok(out.model_dump(mode="json"))


@router.get("/{paper_id}")
async def get_user_paper(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """整卷详情（含题目）。"""
    detail = await user_paper_service.get_paper_detail(
        db, paper_id=paper_id, student_id=current_user.id
    )
    if detail is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(detail.model_dump(mode="json"))


@router.get("/wrongs")
async def list_paper_wrong_questions(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """整卷错题列表（is_wrong=True）。供前端错题本"整卷"tab 调用。"""
    from app.services.wrong_question_service import list_paper_wrongs
    items, total = await list_paper_wrongs(
        db, student_id=current_user.id, skip=skip, limit=limit
    )
    return make_ok({
        "items": [
            {
                "id": str(i.id),
                "stem": i.stem,
                "question_type": i.question_type,
                "is_mastered": i.is_mastered,
                "source_label": i.source_label,
            }
            for i in items
        ],
        "total": total,
    })
