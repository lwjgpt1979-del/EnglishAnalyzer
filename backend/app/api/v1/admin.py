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
from app.models.d5_learning import VocabularyWord
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
from app.schemas.vocabulary import (
    AdminVocabMediaItem,
    AdminVocabMediaListOut,
    VocabMediaReviewRequest,
    VocabMediaUpdateRequest,
)
from app.schemas.institution import (
    AdminInstitutionCreate,
    AdminInstitutionOut,
    ApproveInstitutionRequest,
    ApproveInstitutionResult,
)
from app.services import (
    admin_auth_service,
    admin_institution_service,
    admin_stats_service,
    curriculum_service,
    essay_service,
    pricing_service,
    question_service,
    teacher_service,
    vocab_media_service,
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


@router.get("/essay-templates", response_model=BaseResponse[dict])
async def get_essay_templates(db: DbDep, admin: AdminDep):
    """读作文精修模板/范文配置（未配则返回内置）。"""
    return make_ok(await essay_service.get_all_templates_config(db))


@router.put("/essay-templates", response_model=BaseResponse[dict])
async def update_essay_templates(body: dict, db: DbDep, admin: AdminDep):
    """运营改作文精修模板/范文（题型→{template,samples}）。"""
    v = await essay_service.set_all_templates_config(db, value=body, admin_id=admin.id)
    await db.commit()
    return make_ok(v)


# ─── 词力通图背单词媒体（P1 / D-101）──────────────────────────────────────────

def _to_vocab_media_item(w: VocabularyWord) -> AdminVocabMediaItem:
    return AdminVocabMediaItem(
        word_id=w.id,
        word=w.word,
        image_urls=w.image_urls,
        en_description=w.en_description,
        word_audio_url=w.word_audio_url,
        en_desc_audio_url=w.en_desc_audio_url,
        media_status=str(w.media_status),
    )


@router.post("/vocab/{word_id}/generate-media", response_model=BaseResponse[AdminVocabMediaItem])
async def generate_vocab_media(word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """为单词生成图背媒体（英文描述+多图+双音频，dev-mock）。默认进 draft。"""
    w = await vocab_media_service.generate_for_word(db, word_id=word_id)
    await db.commit()
    return make_ok(_to_vocab_media_item(w))


@router.get("/vocab", response_model=BaseResponse[AdminVocabMediaListOut])
async def list_vocab_media(
    db: DbDep, admin: AdminDep,
    media_status: str = "draft", skip: int = 0, limit: int = 20,
):
    """按媒体状态分页查单词。默认看待审草稿。"""
    rows, total = await vocab_media_service.list_words_for_media_review(
        db, media_status=media_status, skip=skip, limit=limit,
    )
    return make_ok(AdminVocabMediaListOut(
        total=total, items=[_to_vocab_media_item(w) for w in rows],
    ))


@router.post("/vocab/{word_id}/media/review", response_model=BaseResponse[AdminVocabMediaItem])
async def review_vocab_media(word_id: uuid.UUID, body: VocabMediaReviewRequest, db: DbDep, admin: AdminDep):
    """审核单词媒体：approve→published，reject→retired。"""
    w = await vocab_media_service.review_word_media(db, word_id=word_id, approve=body.approve)
    await db.commit()
    return make_ok(_to_vocab_media_item(w))


@router.put("/vocab/{word_id}/media", response_model=BaseResponse[AdminVocabMediaItem])
async def update_vocab_media(word_id: uuid.UUID, body: VocabMediaUpdateRequest, db: DbDep, admin: AdminDep):
    """编辑单词媒体（图/英文描述/音频）。"""
    w = await vocab_media_service.update_word_media(
        db, word_id=word_id, image_urls=body.image_urls, en_description=body.en_description,
        word_audio_url=body.word_audio_url, en_desc_audio_url=body.en_desc_audio_url,
    )
    await db.commit()
    return make_ok(_to_vocab_media_item(w))


# ─── 机构入驻审核（D-123）──────────────────────────────────────────────────

@router.post("/institutions", response_model=BaseResponse[AdminInstitutionOut])
async def admin_create_institution(body: AdminInstitutionCreate, db: DbDep, admin: AdminDep):
    inst = await admin_institution_service.create_institution(
        db, name=body.name, contact_phone=body.contact_phone,
        province_code=body.province_code, city_code=body.city_code, address=body.address)
    await db.commit()
    return make_ok(AdminInstitutionOut.model_validate(inst))


@router.get("/institutions", response_model=BaseResponse[list[AdminInstitutionOut]])
async def admin_list_institutions(db: DbDep, admin: AdminDep, status: str | None = None):
    rows = await admin_institution_service.list_institutions(db, status=status)
    return make_ok([AdminInstitutionOut.model_validate(i) for i in rows])


@router.post("/institutions/{institution_id}/approve",
             response_model=BaseResponse[ApproveInstitutionResult])
async def admin_approve_institution(
    institution_id: uuid.UUID, body: ApproveInstitutionRequest, db: DbDep, admin: AdminDep,
):
    inst, username, password = await admin_institution_service.approve_institution(
        db, institution_id=institution_id, admin_username=body.admin_username)
    await db.commit()
    return make_ok(ApproveInstitutionResult(
        institution_id=inst.id, admin_username=username, password=password))


@router.post("/institutions/{institution_id}/reject", response_model=BaseResponse[AdminInstitutionOut])
async def admin_reject_institution(institution_id: uuid.UUID, db: DbDep, admin: AdminDep):
    inst = await admin_institution_service.reject_institution(db, institution_id=institution_id)
    await db.commit()
    return make_ok(AdminInstitutionOut.model_validate(inst))
