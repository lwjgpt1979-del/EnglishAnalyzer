"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, require_role
from app.models.d1_users import User
from app.schemas.auth import AdminLoginRequest, TokenResponse
from app.models.d11_v2_curriculum import KnowledgePointContent
from app.models.d12_v2_exams import SimulatedQuestion
from app.schemas.admin import AdminOverviewOut
from app.schemas.base import BaseResponse, make_ok
from app.schemas.curriculum import (
    AdminContentItem,
    AdminContentListOut,
    ContentReviewRequest,
    ContentUpdateRequest,
)
from app.schemas.questions import (
    AdminQuestionItem,
    AdminQuestionListOut,
    QuestionReviewRequest,
)
from app.schemas.semesters import SemesterPricing, SemesterPricingUpdate
from app.schemas.teacher import CertReviewRequest, TeacherProfileOut
from app.services import (
    admin_auth_service,
    admin_stats_service,
    curriculum_service,
    pricing_service,
    question_service,
    teacher_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminDep = Annotated[User, Depends(require_role("platform_admin"))]
DbDep = Annotated[AsyncSession, Depends(get_db)]


# ─── 管理员登录（M5 / D-098）：账号密码 → JWT，无需 AdminDep（登录入口）──────

@router.post("/auth/login", response_model=BaseResponse[TokenResponse])
async def admin_login(body: AdminLoginRequest, db: DbDep):
    user = await admin_auth_service.authenticate(
        db, username=body.username, password=body.password,
    )
    if user is None:
        raise AppError(code=401, message="用户名或密码错误")
    return make_ok(TokenResponse(
        access_token=create_access_token(str(user.id), str(user.role)),
        refresh_token=create_refresh_token(str(user.id)),
    ))


# ─── 数据大盘概览（M5 / D-099）──────────────────────────────────────────────

@router.get("/overview", response_model=BaseResponse[AdminOverviewOut])
async def get_overview(db: DbDep, admin: AdminDep):
    """运营概览：仿真题/内容各状态计数 + 用户数 + 已支付订单数。"""
    return make_ok(await admin_stats_service.get_overview(db))


def _to_content_item(r: KnowledgePointContent) -> AdminContentItem:
    return AdminContentItem(
        id=r.id,
        knowledge_point_id=r.knowledge_point_id,
        dimension=str(r.dimension),
        content_md=r.content_md,
        audio_url=r.audio_url,
        status=str(r.status),
        generated_by=str(r.generated_by),
    )


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


# ─── 知识点内容审核/编辑（M5）────────────────────────────────────────────────

@router.get("/contents", response_model=BaseResponse[AdminContentListOut])
async def list_contents_for_review(
    db: DbDep,
    admin: AdminDep,
    status: str = "draft",
    kp_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
):
    """运营按状态分页查知识点内容（含正文）。默认看待审草稿。"""
    rows, total = await curriculum_service.list_contents_for_review(
        db, status=status, kp_id=kp_id, skip=skip, limit=limit,
    )
    return make_ok(AdminContentListOut(
        total=total, items=[_to_content_item(r) for r in rows],
    ))


@router.post("/contents/{content_id}/review", response_model=BaseResponse[AdminContentItem])
async def review_content(
    content_id: uuid.UUID,
    body: ContentReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    """审核一条知识点内容：approve→published，reject→retired。"""
    r = await curriculum_service.review_content(
        db, content_id=content_id, approve=body.approve, reviewer_id=admin.id,
    )
    await db.commit()
    return make_ok(_to_content_item(r))


@router.put("/contents/{content_id}", response_model=BaseResponse[AdminContentItem])
async def update_content(
    content_id: uuid.UUID,
    body: ContentUpdateRequest,
    db: DbDep,
    admin: AdminDep,
):
    """编辑知识点内容正文 / 音频 URL（运营人工修订）。"""
    r = await curriculum_service.update_content(
        db, content_id=content_id, content_md=body.content_md, audio_url=body.audio_url,
    )
    await db.commit()
    return make_ok(_to_content_item(r))


# ─── 学期定价配置（M5）────────────────────────────────────────────────────────

@router.get("/pricing", response_model=BaseResponse[SemesterPricing])
async def get_pricing(db: DbDep, admin: AdminDep):
    """读当前学期会员定价（basic/pro/promax 元/学期）。"""
    return make_ok(await pricing_service.get_semester_pricing(db))


@router.put("/pricing", response_model=BaseResponse[SemesterPricing])
async def update_pricing(body: SemesterPricingUpdate, db: DbDep, admin: AdminDep):
    """运营改学期会员定价（三档单价，正整数）。"""
    updated = await pricing_service.update_semester_pricing(
        db, pricing=SemesterPricing(basic=body.basic, pro=body.pro, promax=body.promax),
        updated_by=admin.id,
    )
    await db.commit()
    return make_ok(updated)
