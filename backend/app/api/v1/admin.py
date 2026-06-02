"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.models.d12_v2_exams import SimulatedQuestion
from app.schemas.base import BaseResponse, make_ok
from app.schemas.questions import (
    AdminQuestionItem,
    AdminQuestionListOut,
    QuestionReviewRequest,
)
from app.schemas.teacher import CertReviewRequest, TeacherProfileOut
from app.services import question_service, teacher_service

router = APIRouter(prefix="/admin", tags=["admin"])

AdminDep = Annotated[User, Depends(require_role("platform_admin"))]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _to_admin_item(r: SimulatedQuestion) -> AdminQuestionItem:
    return AdminQuestionItem(
        id=r.id,
        knowledge_point_id=r.knowledge_point_id,
        question_type=str(r.question_type),
        stem=r.stem,
        options=r.options,
        answer=r.answer,
        explanation=r.explanation,
        difficulty=r.difficulty,
        dimension=str(r.dimension) if r.dimension is not None else None,
        status=str(r.status),
    )


@router.post("/teachers/{teacher_id}/review", response_model=BaseResponse[TeacherProfileOut])
async def review_teacher_cert(
    teacher_id: uuid.UUID,
    body: CertReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    teacher = await teacher_service.review_cert(
        db, teacher_id=teacher_id, approve=body.approve, reason=body.reason,
    )
    await db.commit()
    return make_ok(TeacherProfileOut(
        user_id=teacher.id, subject=teacher.subject,
        cert_status=str(teacher.cert_status),
        cert_doc_url=teacher.cert_doc_url,
        max_students=teacher.max_students,
    ))


# ─── 仿真题审核发布流（M5）─────────────────────────────────────────────────

@router.get("/questions", response_model=BaseResponse[AdminQuestionListOut])
async def list_questions_for_review(
    db: DbDep,
    admin: AdminDep,
    status: str = "draft",
    kp_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
):
    """运营按状态分页查仿真题（含 answer，仅运营可见）。默认看待审草稿。"""
    rows, total = await question_service.list_questions_for_review(
        db, status=status, kp_id=kp_id, skip=skip, limit=limit,
    )
    return make_ok(AdminQuestionListOut(
        total=total, items=[_to_admin_item(r) for r in rows],
    ))


@router.post("/questions/{question_id}/review", response_model=BaseResponse[AdminQuestionItem])
async def review_question(
    question_id: uuid.UUID,
    body: QuestionReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    """审核一道仿真题：approve→published，reject→retired。"""
    r = await question_service.review_question(
        db, question_id=question_id, approve=body.approve,
    )
    await db.commit()
    return make_ok(_to_admin_item(r))
