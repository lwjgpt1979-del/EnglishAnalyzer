"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
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
from app.schemas.teacher import (
    AdminTeacherItem,
    AdminTeacherListOut,
    CertReviewRequest,
    TeacherProfileOut,
)
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


@router.get("/teachers", response_model=BaseResponse[AdminTeacherListOut])
async def list_teachers_admin(
    db: DbDep,
    admin: AdminDep,
    cert_status: str | None = Query(None, description="uncertified/pending/certified/rejected，空=全部"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """列出所有老师（可按认证状态筛选）。"""
    rows, total = await teacher_service.list_teachers_for_admin(
        db, cert_status=cert_status, skip=skip, limit=limit,
    )
    items = [
        AdminTeacherItem(
            teacher_id=t.id,
            nickname=u.nickname,
            phone=u.phone,
            subject=t.subject,
            cert_status=str(t.cert_status),
            cert_doc_url=t.cert_doc_url,
            max_students=t.max_students,
            institution_id=t.institution_id,
            monthly_paper_quota=t.monthly_paper_quota,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for t, u in rows
    ]
    return make_ok(AdminTeacherListOut(total=total, items=items))


@router.post("/teachers/{teacher_id}/review", response_model=BaseResponse[AdminTeacherItem])
async def review_teacher_cert(
    teacher_id: uuid.UUID,
    body: CertReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    """审核老师认证：approve=True→certified，False→rejected。"""
    from app.models.d1_users import User as _User
    teacher = await teacher_service.review_cert(
        db, teacher_id=teacher_id, approve=body.approve, reason=body.reason,
    )
    await db.commit()
    user = await db.get(_User, teacher_id)
    return make_ok(AdminTeacherItem(
        teacher_id=teacher.id,
        nickname=user.nickname if user else None,
        phone=user.phone if user else None,
        subject=teacher.subject,
        cert_status=str(teacher.cert_status),
        cert_doc_url=teacher.cert_doc_url,
        max_students=teacher.max_students,
        institution_id=teacher.institution_id,
        monthly_paper_quota=teacher.monthly_paper_quota,
        created_at=user.created_at.isoformat() if user and user.created_at else "",
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


# ── V2 课程单元管理 ────────────────────────────────────────────────────────────

@router.get("/curriculum/units")
async def list_curriculum_units(db: DbDep, admin: AdminDep):
    """列出所有课程单元 + 内容完成度统计，供 Admin 内容生成触发。"""
    stats = await curriculum_service.list_units_with_stats(db)
    return make_ok([
        {
            "unit_id": str(s.unit_id),
            "textbook_version": s.textbook_version,
            "grade": s.grade,
            "semester": s.semester,
            "unit_no": s.unit_no,
            "unit_title": s.unit_title,
            "kp_count": s.kp_count,
            "content_count": s.content_count,
            "content_rate": s.content_rate,
        }
        for s in stats
    ])


@router.post("/curriculum/units/{unit_id}/generate")
async def generate_unit_content(
    unit_id: uuid.UUID,
    db: DbDep,
    admin: AdminDep,
):
    """触发 AI 生成指定单元的课程内容（dev mock 即时；生产约 5-15s）。

    生成内容 status='draft'，需在 ContentsReview 审核发布后学生才可见。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.services import curriculum_ai_service

    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="单元不存在")

    ai_unit = await curriculum_ai_service.generate_unit(
        textbook_version=unit.textbook_version,
        grade=str(unit.grade),
        semester=str(unit.semester),
        unit_no=unit.unit_no,
    )
    await curriculum_service.persist_unit(db, ai_unit=ai_unit, content_status="draft")
    await db.commit()

    # 返回更新后的统计
    stats = await curriculum_service.list_units_with_stats(db)
    stat = next((s for s in stats if s.unit_id == unit_id), None)
    return make_ok({
        "unit_id": str(unit_id),
        "kp_count": stat.kp_count if stat else 0,
        "content_count": stat.content_count if stat else 0,
        "content_rate": stat.content_rate if stat else 0.0,
    })


# ─── V2 M28：真题试卷管理（版权规避：真题内部存储，仅对外暴露仿真题）──────────

from pydantic import BaseModel as _BM, Field as _F
from app.models.d12_v2_exams import ExamPaper as _EP, SimulatedQuestion as _SQ


class ExamPaperCreate(_BM):
    title: str
    textbook_version: str
    grade: str
    semester: str
    region: str | None = None
    paper_url: str | None = None  # 已上传到 OSS 的 URL


class ExamPaperOut(_BM):
    id: str
    title: str
    textbook_version: str
    grade: str
    semester: str
    region: str | None = None
    paper_url: str | None = None
    status: str
    sim_count: int = 0
    created_at: str

    model_config = {"from_attributes": True}


class ExamPaperListOut(_BM):
    items: list[ExamPaperOut]
    total: int


@router.post("/exam-papers", response_model=BaseResponse[ExamPaperOut])
async def create_exam_paper(body: ExamPaperCreate, db: DbDep, admin: AdminDep):
    """平台管理员录入一份真题试卷（内部存储，不对外暴露原题）。"""
    from sqlalchemy import func
    paper = _EP(
        id=uuid.uuid4(),
        source="official_seed",
        uploader_id=admin.id,
        textbook_version=body.textbook_version,
        grade=body.grade,
        semester=body.semester,
        region=body.region,
        title=body.title,
        paper_url=body.paper_url,
        status="draft",
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    return make_ok(ExamPaperOut(
        id=str(paper.id),
        title=paper.title,
        textbook_version=paper.textbook_version,
        grade=str(paper.grade),
        semester=str(paper.semester),
        region=paper.region,
        paper_url=paper.paper_url,
        status=str(paper.status),
        sim_count=0,
        created_at=paper.created_at.isoformat(),
    ))


@router.get("/exam-papers", response_model=BaseResponse[ExamPaperListOut])
async def list_exam_papers(
    db: DbDep,
    admin: AdminDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """列出所有真题试卷（含仿真题数量统计）。"""
    from sqlalchemy import func, select as _s
    from app.models.d12_v2_exams import ExamQuestion as _EQ

    total: int = (await db.execute(
        _s(func.count()).select_from(_EP)
    )).scalar_one()

    rows = (await db.execute(
        _s(_EP).order_by(_EP.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()

    items = []
    for p in rows:
        # 统计该试卷关联的仿真题数（通过 exam_questions → simulated_questions）
        sim_cnt: int = (await db.execute(
            _s(func.count(_SQ.id))
            .join(_EQ, _EQ.id == _SQ.source_exam_question_id)
            .where(_EQ.paper_id == p.id)
        )).scalar_one()
        items.append(ExamPaperOut(
            id=str(p.id),
            title=p.title,
            textbook_version=p.textbook_version,
            grade=str(p.grade),
            semester=str(p.semester),
            region=p.region,
            paper_url=p.paper_url,
            status=str(p.status),
            sim_count=sim_cnt,
            created_at=p.created_at.isoformat(),
        ))
    return make_ok(ExamPaperListOut(items=items, total=total))


@router.post("/exam-papers/{paper_id}/generate", response_model=BaseResponse[dict])
async def generate_sim_questions_from_paper(
    paper_id: uuid.UUID, db: DbDep, admin: AdminDep
):
    """触发 AI 依据真题生成仿真题（规避版权：仿真题与原题措辞不同）。

    MVP 实现：基于 ExamQuestion 记录（若存在）批量创建 SimulatedQuestion draft。
    生产版本接入 LLM 改写服务。
    """
    from sqlalchemy import select as _s
    from app.models.d12_v2_exams import ExamQuestion as _EQ

    paper = (await db.execute(
        _s(_EP).where(_EP.id == paper_id)
    )).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在")

    # 取该试卷下所有 exam_questions
    eq_rows = (await db.execute(
        _s(_EQ).where(_EQ.paper_id == paper_id)
    )).scalars().all()

    # 取第一个知识点（MVP：用首个可用 KP）
    from app.models.d11_v2_curriculum import KnowledgePoint as _KP
    kp = (await db.execute(_s(_KP).limit(1))).scalar_one_or_none()
    if kp is None:
        raise AppError(code=400, message="暂无知识点，请先生成课程内容")

    created = 0
    for eq in eq_rows:
        # 检查是否已有仿真题
        existing = (await db.execute(
            _s(_SQ).where(_SQ.source_exam_question_id == eq.id)
        )).scalar_one_or_none()
        if existing:
            continue
        db.add(_SQ(
            id=uuid.uuid4(),
            source_exam_question_id=eq.id,
            knowledge_point_id=kp.id,
            question_type=eq.question_type,
            stem=f"[仿真] {eq.stem}",
            options=eq.options,
            answer=eq.answer or "A",
            explanation=eq.explanation,
            difficulty=eq.difficulty or 3,
            status="draft",
        ))
        created += 1

    await db.commit()
    return make_ok({"paper_id": str(paper_id), "sim_questions_created": created})
