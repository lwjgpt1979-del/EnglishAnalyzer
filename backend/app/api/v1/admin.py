"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from pydantic import BaseModel
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
from app.schemas.kp import (
    ApproveCandidateRequest,
    KpCandidateItem,
    KpCandidateListOut,
    KpNodeItem,
    KpNodeListOut,
    MergeCandidateRequest,
    RejectCandidateRequest,
    UnitExtractOut,
    UnitNodeItem,
    UnitNodeListOut,
    PlatformQuestionItem,
    PlatformQuestionListOut,
    GenSimOut,
    ReviewRequest,
    VocabListCreate,
    VocabListOut,
    VocabListsOut,
    VocabItemsIn,
    VocabItemOut,
    VocabItemsOut,
    NodeResourceItem,
    NodeResourceListOut,
    AddResourceIn,
    UpdateResourceIn,
)
from app.services import (
    admin_auth_service,
    admin_institution_service,
    admin_stats_service,
    curriculum_service,
    essay_service,
    kp_candidate_service,
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
async def admin_login(body: AdminLoginRequest, request: Request, db: DbDep):
    # 防爆破限流：同 IP 20 次/5min、同用户名 10 次/5min
    from app.services import rate_limit_service as _rl
    ip = _rl.client_ip(request)
    await _rl.hit(db, key=f"admin_login:ip:{ip}", limit=20, window_seconds=300,
                  message="登录尝试过于频繁，请 5 分钟后再试")
    await _rl.hit(db, key=f"admin_login:user:{(body.username or '').lower()}", limit=10,
                  window_seconds=300, message="该账号登录尝试过于频繁，请 5 分钟后再试")
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

@router.get("/dashboard", response_model=None)
async def admin_dashboard(db: DbDep, admin: AdminDep):
    """数据大盘（§5.5）：用户/角色/地区/会员/营收/今日功能使用/机构。"""
    from app.services import dashboard_service
    return make_ok(await dashboard_service.get_dashboard(db))


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


# ─── 候选知识点审核（R0.4 KP-First）─────────────────────────────────────────────

def _to_kp_candidate_item(c) -> KpCandidateItem:
    return KpCandidateItem(
        id=c.id, raw_name=c.raw_name, name_norm=c.name_norm,
        suggested_axis=c.suggested_axis, suggested_stage=c.suggested_stage,
        occur_count=c.occur_count, source_type=c.source_type,
        context_sample=c.context_sample, status=c.status,
    )


def _to_kp_node_item(n) -> KpNodeItem:
    return KpNodeItem(
        id=n.id, axis=n.axis, node_kind=n.node_kind, name=n.name,
        code=n.code, applicable_stages=n.applicable_stages,
    )


@router.get("/kp-candidates", response_model=BaseResponse[KpCandidateListOut])
async def list_kp_candidates(
    db: DbDep,
    admin: AdminDep,
    status: str = "pending",
    axis: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    """候选知识点队列(默认 pending,高频 occur_count 优先)。"""
    rows, total = await kp_candidate_service.list_candidates(
        db, status=status, axis=axis, skip=skip, limit=limit,
    )
    return make_ok(KpCandidateListOut(
        total=total, items=[_to_kp_candidate_item(r) for r in rows],
    ))


@router.get("/kp-nodes", response_model=BaseResponse[KpNodeListOut])
async def list_kp_nodes(
    db: DbDep,
    admin: AdminDep,
    axis: str | None = None,
    stage: str | None = None,
    q: str | None = None,
    limit: int = 20,
):
    """归并目标选择器:按 axis/学段/名称模糊查 active 节点。"""
    rows = await kp_candidate_service.list_nodes(db, axis=axis, stage=stage, q=q, limit=limit)
    return make_ok(KpNodeListOut(total=len(rows), items=[_to_kp_node_item(r) for r in rows]))


@router.post("/kp-candidates/{candidate_id}/approve", response_model=BaseResponse[KpNodeItem])
async def approve_kp_candidate(
    candidate_id: uuid.UUID,
    body: ApproveCandidateRequest,
    db: DbDep,
    admin: AdminDep,
):
    """通过 → 建正式节点 + 候选名进别名。"""
    node = await kp_candidate_service.approve(
        db, candidate_id=candidate_id, axis=body.axis, stage=body.stage,
        node_kind=body.node_kind, parent_id=body.parent_id, reviewer_id=admin.id,
    )
    await db.commit()
    return make_ok(_to_kp_node_item(node))


@router.post("/kp-candidates/{candidate_id}/merge", response_model=BaseResponse[KpNodeItem])
async def merge_kp_candidate(
    candidate_id: uuid.UUID,
    body: MergeCandidateRequest,
    db: DbDep,
    admin: AdminDep,
):
    """归并 → 候选名作为目标节点的别名(治碎片化)。"""
    node = await kp_candidate_service.merge(
        db, candidate_id=candidate_id, target_node_id=body.target_node_id,
        reviewer_id=admin.id,
    )
    await db.commit()
    return make_ok(_to_kp_node_item(node))


@router.post("/kp-candidates/{candidate_id}/reject", response_model=BaseResponse[KpCandidateItem])
async def reject_kp_candidate(
    candidate_id: uuid.UUID,
    body: RejectCandidateRequest,
    db: DbDep,
    admin: AdminDep,
):
    """驳回(理由必填)。"""
    cand = await kp_candidate_service.reject(
        db, candidate_id=candidate_id, reason=body.reason, reviewer_id=admin.id,
    )
    await db.commit()
    return make_ok(_to_kp_candidate_item(cand))


# ─── 学期定价配置（M5）────────────────────────────────────────────────────────

@router.get("/pricing", response_model=BaseResponse[SemesterPricing])
async def get_pricing(db: DbDep, admin: AdminDep):
    """读当前学期会员定价（basic/pro/promax 元/学期）。"""
    return make_ok(await pricing_service.get_semester_pricing(db))


@router.put("/pricing", response_model=BaseResponse[SemesterPricing])
async def update_pricing(body: SemesterPricingUpdate, db: DbDep, admin: AdminDep):
    """运营改学期会员定价（三档单价，正整数）。"""
    updated = await pricing_service.update_semester_pricing(
        db, pricing=SemesterPricing(
            basic=body.basic, pro=body.pro, promax=body.promax,
            list_basic=body.list_basic, list_pro=body.list_pro, list_promax=body.list_promax),
        updated_by=admin.id,
    )
    await db.commit()
    return make_ok(updated)


# ─── 听力语速三档（小学/初中/高中，speed_ratio）────────────────────────────
class TtsSpeedConfig(BaseModel):
    primary: float
    junior: float
    senior: float


@router.get("/tts-speed", response_model=BaseResponse[TtsSpeedConfig])
async def get_tts_speed(db: DbDep, admin: AdminDep):
    """读当前听力语速三档配置。"""
    from app.services import tts_service
    return make_ok(TtsSpeedConfig(**await tts_service.get_listening_speeds(db)))


@router.put("/tts-speed", response_model=BaseResponse[TtsSpeedConfig])
async def update_tts_speed(body: TtsSpeedConfig, db: DbDep, admin: AdminDep):
    """运营改听力语速三档（speed_ratio，建议 0.6~1.5；单词统一用初中档）。"""
    from app.services import tts_service
    for v in (body.primary, body.junior, body.senior):
        if not (0.5 <= v <= 2.0):
            raise AppError(code=400, message="语速倍率需在 0.5~2.0 之间")
    saved = await tts_service.set_listening_speeds(
        db, speeds=body.model_dump(), updated_by=admin.id)
    await db.commit()
    return make_ok(TtsSpeedConfig(**saved))


class TtsVoicesConfig(BaseModel):
    male: list[str]
    female: list[str]


@router.get("/tts-voices", response_model=BaseResponse[TtsVoicesConfig])
async def get_tts_voices(db: DbDep, admin: AdminDep):
    """读当前男/女音色池（火山 bigtts voice_type 列表）。"""
    from app.services import tts_service
    return make_ok(TtsVoicesConfig(**await tts_service.get_voices(db)))


@router.put("/tts-voices", response_model=BaseResponse[TtsVoicesConfig])
async def update_tts_voices(body: TtsVoicesConfig, db: DbDep, admin: AdminDep):
    """运营改男/女音色池。对话听力按说话人性别选音色，单词按词哈希稳定取一个。"""
    from app.services import tts_service
    male = [v.strip() for v in body.male if v.strip()]
    female = [v.strip() for v in body.female if v.strip()]
    if not male or not female:
        raise AppError(code=400, message="男、女音色各至少配 1 个")
    saved = await tts_service.set_voices(
        db, male=male, female=female, updated_by=admin.id)
    await db.commit()
    return make_ok(TtsVoicesConfig(**saved))


_TTS_PREVIEW_SAMPLE = "Hello! Welcome to English learning. Let's practice together."


@router.get("/tts-preview", response_model=BaseResponse[dict])
async def tts_preview(
    db: DbDep,
    admin: AdminDep,
    voice: str = Query("", description="指定音色 voice_type；空则按样本句哈希取池内音色"),
    speed: float = Query(1.0, description="语速倍率 0.5~2.0"),
    text: str = Query("", description="试听文本；空用默认样本句"),
):
    """合成一句样本并返回 COS 直链，供后台「试听」即点即播。"""
    from app.services import tts_service
    spd = min(2.0, max(0.5, speed))
    sample = (text or _TTS_PREVIEW_SAMPLE).strip()[:200]
    url = await tts_service.get_or_create_audio_url(
        sample, voice=(voice.strip() or None), speed=spd)
    if not url:
        raise AppError(code=400, message="试听失败：音色未授权或语音/COS 未配置")
    return make_ok({"url": url})


@router.get("/speaking-config", response_model=BaseResponse[dict])
async def get_speaking_config(db: DbDep, admin: AdminDep):
    """读口语对话场景配置（特殊/通用/学期 的启用开关 + AI 提示词）。"""
    from app.services import speaking_dialogue_service
    return make_ok(await speaking_dialogue_service.get_speaking_config(db))


@router.put("/speaking-config", response_model=BaseResponse[dict])
async def update_speaking_config(body: dict, db: DbDep, admin: AdminDep):
    """运营改口语场景配置。结构容错合并，缺失项回落默认。"""
    from app.services import speaking_dialogue_service
    saved = await speaking_dialogue_service.set_speaking_config(
        db, config=body or {}, updated_by=admin.id)
    await db.commit()
    return make_ok(saved)


@router.get("/speaking-config/semesters", response_model=BaseResponse[list])
async def speaking_config_semesters(db: DbDep, admin: AdminDep):
    """学期场景分级规则编辑用：教材/年级/学期/单元 选择树。"""
    from app.services import speaking_dialogue_service
    return make_ok(await speaking_dialogue_service.semester_scope_tree(db))


@router.get("/tts-stats", response_model=BaseResponse[dict])
async def tts_stats(db: DbDep, admin: AdminDep):
    """TTS 用量看板：COS 上 tts/ 已生成音频数 + 存储用量 + 当前预热进度。"""
    from app.services import tts_service
    usage = await tts_service.cos_usage()
    return make_ok({"cos": usage, "prewarm": tts_service.prewarm_status()})


@router.get("/tts-prewarm/semesters", response_model=BaseResponse[list])
async def tts_prewarm_semesters(db: DbDep, admin: AdminDep):
    """可预热的学期列表（有词汇的，按词数倒序）。"""
    from app.services import tts_service
    return make_ok(await tts_service.prewarm_semesters(db))


class TtsPrewarmIn(BaseModel):
    textbook_version: str
    grade: str
    semester: str
    scope: str = "vocab"   # vocab | listening | all
    limit: int = 50


@router.post("/tts-prewarm", response_model=BaseResponse[dict])
async def tts_prewarm(body: TtsPrewarmIn, db: DbDep, admin: AdminDep):
    """按学期后台批量预生成音频入 COS（首播零延迟、控成本）。串行单任务。"""
    from app.services import tts_service
    speed = await tts_service.speed_for_stage_db(db, "junior")
    res = await tts_service.start_prewarm(
        db, textbook_version=body.textbook_version, grade=body.grade,
        semester=body.semester, scope=body.scope, limit=body.limit, speed=speed)
    return make_ok(res)


@router.get("/tts-prewarm/status", response_model=BaseResponse[dict])
async def tts_prewarm_status(db: DbDep, admin: AdminDep):
    from app.services import tts_service
    return make_ok(tts_service.prewarm_status())


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


class VocabImageConfig(BaseModel):
    batch_size: int = 20
    images_per_word: int = 1
    use_ai_prompt: bool = True
    primary: str
    styles: list[str]


@router.get("/vocab-image-config", response_model=BaseResponse[VocabImageConfig])
async def get_vocab_image_config(db: DbDep, admin: AdminDep):
    """读配图提示词配置（主要要求 + 随机风格 + 批量数量）。"""
    return make_ok(VocabImageConfig(**await vocab_media_service.get_image_config(db)))


@router.put("/vocab-image-config", response_model=BaseResponse[VocabImageConfig])
async def update_vocab_image_config(body: VocabImageConfig, db: DbDep, admin: AdminDep):
    """改配图提示词配置。"""
    saved = await vocab_media_service.set_image_config(
        db, config=body.model_dump(), updated_by=admin.id)
    await db.commit()
    return make_ok(VocabImageConfig(**saved))


@router.post("/vocab-image/batch", response_model=BaseResponse[dict])
async def start_vocab_image_batch(db: DbDep, admin: AdminDep):
    """对未配图的单词，按配置批量生成配图（后台串行）。"""
    return make_ok(await vocab_media_service.start_batch_image_gen(db))


@router.get("/vocab-image/batch/status", response_model=BaseResponse[dict])
async def vocab_image_batch_status(db: DbDep, admin: AdminDep):
    return make_ok(vocab_media_service.batch_status())


@router.post("/vocab-audio/backfill", response_model=BaseResponse[dict])
async def backfill_vocab_audio(db: DbDep, admin: AdminDep):
    """给已有例句/短语/单词但缺音频的词补预生成语音(火山→COS缓存)，写回词库。"""
    return make_ok(await vocab_media_service.backfill_audio(db))


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
async def admin_list_institutions(
    db: DbDep, admin: AdminDep, status: str | None = None, source: str | None = None,
):
    rows = await admin_institution_service.list_institutions(db, status=status, source=source)
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
    # R1:生成后自动对齐知识图谱(防御式,失败不阻断生成)
    from app.services import curriculum_kp_service
    await curriculum_kp_service.extract_for_ai_unit(db, unit_id=unit_id, ai_unit=ai_unit)
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


# ─── 单元 ↔ 知识图谱节点（R1 教材接入）─────────────────────────────────────────

@router.get("/curriculum/units/{unit_id}/nodes", response_model=BaseResponse[UnitNodeListOut])
async def list_unit_nodes_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """查看该单元已对齐的知识图谱节点(unit_node 边)。"""
    from app.services import curriculum_kp_service
    rows = await curriculum_kp_service.list_unit_nodes(db, unit_id=unit_id)
    return make_ok(UnitNodeListOut(total=len(rows), items=[UnitNodeItem(**r) for r in rows]))


@router.post("/curriculum/units/{unit_id}/extract-kps", response_model=BaseResponse[UnitExtractOut])
async def reextract_unit_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """重跑对齐:从该单元已有知识点名再走受控匹配(命中建边/未命中候选)。幂等。"""
    from app.services import curriculum_kp_service
    res = await curriculum_kp_service.reextract_unit(db, unit_id=unit_id)
    await db.commit()
    return make_ok(UnitExtractOut(**res.stats))


# ─── 平台题管理（R2 真题/仿真接入）──────────────────────────────────────────────

def _to_pq_item(q) -> PlatformQuestionItem:
    return PlatformQuestionItem(
        id=q.id, type=q.type, parent_real_id=q.parent_real_id, is_fallback=q.is_fallback,
        question_type=q.question_type, stem=q.stem, answer=q.answer,
        difficulty=q.difficulty, status=q.status,
    )


@router.get("/platform-questions", response_model=BaseResponse[PlatformQuestionListOut])
async def list_platform_questions_api(
    db: DbDep, admin: AdminDep,
    type: str | None = None, status: str | None = None,
    node_id: uuid.UUID | None = None, skip: int = 0, limit: int = 20,
):
    """平台题分页查询(真题/仿真,可按 type/status/node 过滤)。"""
    from app.services import platform_question_service as pqs
    rows, total = await pqs.list_platform_questions(
        db, type=type, status=status, node_id=node_id, skip=skip, limit=limit)
    return make_ok(PlatformQuestionListOut(total=total, items=[_to_pq_item(r) for r in rows]))


@router.post("/platform-questions/{real_id}/gen-sim", response_model=BaseResponse[GenSimOut])
async def gen_sim_from_real_api(real_id: uuid.UUID, db: DbDep, admin: AdminDep, count: int = 3):
    """由真题预生成 N 道仿真(继承母题 KP,parent_real_id 必填)。"""
    from app.services import platform_question_service as pqs
    sim_ids = await pqs.generate_sim_from_real(db, real_id=real_id, count=count)
    await db.commit()
    return make_ok(GenSimOut(generated=len(sim_ids), sim_ids=sim_ids))


@router.post("/platform-questions/{question_id}/review", response_model=BaseResponse[PlatformQuestionItem])
async def review_platform_question_api(
    question_id: uuid.UUID, body: ReviewRequest, db: DbDep, admin: AdminDep,
):
    """审核平台题:approve→published,reject→retired。"""
    from app.services import platform_question_service as pqs
    q = await pqs.review_platform_question(db, question_id=question_id, approve=body.approve)
    await db.commit()
    return make_ok(_to_pq_item(q))


# ─── 知识节点资源管理（R6 资源层补全）────────────────────────────────────────────

def _to_node_resource_item(r) -> NodeResourceItem:
    return NodeResourceItem(
        id=r.id, node_id=r.node_id, resource_type=r.resource_type, dimension=r.dimension,
        title=r.title, content_md=r.content_md, media_url=r.media_url,
        resource_json=r.resource_json, status=r.status,
    )


@router.get("/node-resources", response_model=BaseResponse[NodeResourceListOut])
async def list_node_resources_api(
    db: DbDep, admin: AdminDep, status: str | None = "draft",
    node_id: uuid.UUID | None = None, resource_type: str | None = None,
    skip: int = 0, limit: int = 20,
):
    from app.services import node_resource_service as nrs
    rows, total = await nrs.list_for_review(db, status=status, node_id=node_id,
                                            resource_type=resource_type, skip=skip, limit=limit)
    return make_ok(NodeResourceListOut(total=total, items=[_to_node_resource_item(r) for r in rows]))


@router.post("/node-resources", response_model=BaseResponse[NodeResourceItem])
async def add_node_resource_api(body: AddResourceIn, db: DbDep, admin: AdminDep):
    from app.services import node_resource_service as nrs
    if body.resource_type == "lecture":
        if not body.dimension or not body.content_md:
            raise AppError(code=400, message="lecture 需 dimension + content_md")
        rid = await nrs.upsert_lecture(db, node_id=body.node_id, dimension=body.dimension,
                                       content_md=body.content_md, media_url=body.media_url, status=body.status)
        await db.commit()
        from app.models.d19_node_resource import NodeResource as _NR
        r = (await db.execute(select(_NR).where(_NR.id == rid))).scalar_one()
    else:
        r = await nrs.add_resource(db, node_id=body.node_id, resource_type=body.resource_type,
                                   title=body.title, content_md=body.content_md, media_url=body.media_url,
                                   resource_json=body.resource_json, status=body.status)
        await db.commit()
    return make_ok(_to_node_resource_item(r))


@router.post("/node-resources/{resource_id}/review", response_model=BaseResponse[NodeResourceItem])
async def review_node_resource_api(resource_id: uuid.UUID, body: ReviewRequest, db: DbDep, admin: AdminDep):
    from app.services import node_resource_service as nrs
    r = await nrs.review(db, resource_id=resource_id, approve=body.approve, reviewer_id=admin.id)
    await db.commit()
    return make_ok(_to_node_resource_item(r))


@router.put("/node-resources/{resource_id}", response_model=BaseResponse[NodeResourceItem])
async def update_node_resource_api(resource_id: uuid.UUID, body: UpdateResourceIn, db: DbDep, admin: AdminDep):
    from app.services import node_resource_service as nrs
    r = await nrs.update_resource(db, resource_id=resource_id, content_md=body.content_md,
                                  media_url=body.media_url, title=body.title, resource_json=body.resource_json)
    await db.commit()
    return make_ok(_to_node_resource_item(r))


# ─── 通用词库管理（R5 词汇并入,平台域超管维护）──────────────────────────────────

@router.get("/vocab-lists", response_model=BaseResponse[VocabListsOut])
async def list_vocab_lists_api(db: DbDep, admin: AdminDep, status: str | None = None):
    from app.services import vocab_list_service as vls
    rows = await vls.list_lists(db, status=status)
    return make_ok(VocabListsOut(items=[
        VocabListOut(id=r.id, name=r.name, exam_level=r.exam_level,
                     source_type=r.source_type, status=r.status) for r in rows]))


@router.post("/vocab-lists", response_model=BaseResponse[VocabListOut])
async def create_vocab_list_api(body: VocabListCreate, db: DbDep, admin: AdminDep):
    from app.services import vocab_list_service as vls
    vl = await vls.create_list(db, name=body.name, exam_level=body.exam_level,
                               source_type=body.source_type, maintained_by=admin.id, status=body.status)
    await db.commit()
    return make_ok(VocabListOut(id=vl.id, name=vl.name, exam_level=vl.exam_level,
                                source_type=vl.source_type, status=vl.status))


@router.get("/vocab-lists/{list_id}/items", response_model=BaseResponse[VocabItemsOut])
async def list_vocab_items_api(list_id: uuid.UUID, db: DbDep, admin: AdminDep, skip: int = 0, limit: int = 100):
    from app.services import vocab_list_service as vls
    items = await vls.list_items(db, list_id=list_id, skip=skip, limit=limit)
    return make_ok(VocabItemsOut(total=len(items), items=[VocabItemOut(**it) for it in items]))


@router.post("/vocab-lists/{list_id}/items", response_model=BaseResponse[VocabItemsOut])
async def add_vocab_items_api(list_id: uuid.UUID, body: VocabItemsIn, db: DbDep, admin: AdminDep):
    from app.services import vocab_list_service as vls
    await vls.add_items(db, list_id=list_id, items=[it.model_dump(exclude_none=True) for it in body.items])
    await db.commit()
    items = await vls.list_items(db, list_id=list_id, limit=500)
    return make_ok(VocabItemsOut(total=len(items), items=[VocabItemOut(**it) for it in items]))


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


# ── M2 课程内容 AI 生成 ────────────────────────────────────────────────────────

class GenerateSemesterRequest(_BM):
    textbook_version: str = "译林版"
    grade: str = "小学5年级"
    semester: str = "上"
    unit_count: int = 6
    content_status: str = "published"
    reset: bool = True


@router.post("/curriculum/generate-semester", response_model=BaseResponse[list[dict]])
async def generate_semester_api(
    body: GenerateSemesterRequest,
    db: DbDep,
    admin: AdminDep,
):
    """用真实 AI 生成（或重新生成）一个学期的课程内容（M2）。

    reset=True 先清除该学期已有数据再重建（幂等）。
    content_status="published" 生成后立即对学生可见。
    同步执行，6 单元约 60-90 秒，请耐心等待。
    """
    results = await curriculum_service.generate_semester(
        db,
        textbook_version=body.textbook_version,
        grade=body.grade,
        semester=body.semester,
        unit_count=body.unit_count,
        content_status=body.content_status,
        reset=body.reset,
    )
    await db.commit()
    return make_ok(results)


# ── M3 教材 PDF 上传解析 ──────────────────────────────────────────────────────

from fastapi import UploadFile, File, Form
from app.schemas.pdf_upload import (
    PdfUploadOut, PdfPageListOut, PagePreview,
    GenerateFromPdfRequest, GenerateFromPdfOut, UnitGenerateResult, UnitSegment,
)
from app.services import pdf_upload_service


@router.post("/curriculum/pdf/upload", response_model=BaseResponse[PdfUploadOut])
async def upload_curriculum_pdf(
    admin: AdminDep,
    file: UploadFile = File(..., description="教材 PDF 文件"),
):
    """
    上传教材 PDF，自动检测单元分界。

    返回：
    - file_id：后续生成接口使用
    - auto_split_success：True 表示自动识别到 ≥2 个单元，可直接生成；
      False 表示需调用 /pages 端点查看页面预览后手动划分单元范围。
    - auto_segments：自动识别的单元列表（auto_split_success=False 时为空）
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppError(code=400, message="请上传 PDF 文件（.pdf 后缀）")

    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:  # 100 MB 上限
        raise AppError(code=400, message="PDF 文件过大（上限 100 MB）")

    file_id = pdf_upload_service.save_upload(raw)

    try:
        pages = pdf_upload_service.extract_pages(file_id)
    except Exception as exc:
        pdf_upload_service.delete_upload(file_id)
        raise AppError(code=422, message=f"PDF 文本提取失败：{exc}") from exc

    segments_raw = pdf_upload_service.auto_detect_units(pages)
    auto_ok = segments_raw is not None

    return make_ok(PdfUploadOut(
        file_id=file_id,
        filename=file.filename,
        total_pages=len(pages),
        auto_split_success=auto_ok,
        auto_segments=[UnitSegment(**s) for s in (segments_raw or [])],
    ))


@router.get("/curriculum/pdf/{file_id}/pages", response_model=BaseResponse[PdfPageListOut])
async def get_pdf_pages(file_id: str, admin: AdminDep):
    """
    返回 PDF 各页文本摘要（前 200 字），供人工划定单元起止页使用。

    仅在 upload 返回 auto_split_success=False 时需要调用此接口。
    """
    try:
        previews_raw = pdf_upload_service.get_page_previews(file_id)
    except FileNotFoundError:
        raise AppError(code=404, message=f"PDF 不存在（file_id={file_id}），请重新上传")
    except Exception as exc:
        raise AppError(code=422, message=f"PDF 读取失败：{exc}") from exc

    return make_ok(PdfPageListOut(
        file_id=file_id,
        total_pages=len(previews_raw),
        pages=[PagePreview(**p) for p in previews_raw],
    ))


@router.post("/curriculum/pdf/{file_id}/generate",
             response_model=BaseResponse[GenerateFromPdfOut])
async def generate_from_pdf(
    file_id: str,
    body: GenerateFromPdfRequest,
    db: DbDep,
    admin: AdminDep,
):
    """
    根据上传的 PDF 分片逐单元调用 AI 生成课程内容。

    segments 可来自 upload 返回的 auto_segments，或人工在 /pages 基础上划定。
    每个 segment 单独调用 DeepSeek，将真实单元文本作为上下文。
    成功的单元直接写入数据库（content_status 由请求决定）。
    任一单元失败不影响其他单元继续生成。
    """
    from app.services import curriculum_ai_service

    try:
        _ = pdf_upload_service.extract_pages(file_id)  # 验证文件存在
    except FileNotFoundError:
        raise AppError(code=404, message=f"PDF 不存在（file_id={file_id}），请重新上传")

    results: list[UnitGenerateResult] = []
    success = error = 0

    for seg in body.segments:
        try:
            unit_text = pdf_upload_service.get_unit_text(
                file_id, seg.start_page, seg.end_page,
            )
            ai_unit = await curriculum_ai_service.generate_unit_from_text(
                textbook_version=body.textbook_version,
                grade=body.grade,
                semester=body.semester,
                unit_no=seg.unit_no,
                unit_text=unit_text,
                detected_title=seg.detected_title,
            )
            cu = await curriculum_service.persist_unit(
                db, ai_unit=ai_unit, content_status=body.content_status,
            )
            await db.flush()
            # R1:PDF 上传生成后自动对齐知识图谱(来源 upload_extract;失败不阻断)
            from app.services import curriculum_kp_service
            await curriculum_kp_service.extract_for_ai_unit(
                db, unit_id=cu.id, ai_unit=ai_unit, source="upload_extract",
            )
            results.append(UnitGenerateResult(
                unit_no=seg.unit_no,
                unit_title=ai_unit.unit_title,
                kp_count=len(ai_unit.knowledge_points),
                word_count=len(ai_unit.words),
                status="ok",
            ))
            success += 1
        except Exception as exc:
            results.append(UnitGenerateResult(
                unit_no=seg.unit_no,
                unit_title=seg.detected_title or f"Unit {seg.unit_no}",
                kp_count=0,
                word_count=0,
                status="error",
                error=str(exc),
            ))
            error += 1

    await db.commit()
    return make_ok(GenerateFromPdfOut(
        results=results,
        success_count=success,
        error_count=error,
    ))


# ── M11 主题中心 ──────────────────────────────────────────────────────────────
from pydantic import BaseModel as _ThemeBM
from app.services import theme_service as _theme_svc


class SetThemeRequest(_ThemeBM):
    key: str


@router.get("/themes", response_model=None)
async def admin_list_themes(db: DbDep, admin: AdminDep):
    """列出全部主题预设 + 当前上线主题 key。"""
    return make_ok(await _theme_svc.list_themes(db))


@router.put("/theme", response_model=None)
async def admin_set_theme(body: SetThemeRequest, db: DbDep, admin: AdminDep):
    """设置上线主题（写 system_configs，小程序下次启动生效）。"""
    theme = await _theme_svc.set_active(db, key=body.key, operator_id=admin.id)
    await db.commit()
    return make_ok(theme)


# ── M13 学情退步预警批量推送 ──────────────────────────────────────────────────
from app.services import regression_service as _regression_svc


@router.post("/regression-alerts/run", response_model=None)
async def admin_run_regression_alerts(db: DbDep, admin: AdminDep):
    """批量检测全体学生知识点退步并推送通知（运营/定时调用）。"""
    result = await _regression_svc.run_regression_alerts(db)
    await db.commit()
    return make_ok(result)


# ── 退款 / 申诉审核队列（P3，§4.7）────────────────────────────────────────────
from app.services import refund_service as _refund_svc
from app.schemas.payments import AdminRefundListOut, RefundReviewRequest


@router.get("/refunds", response_model=BaseResponse[AdminRefundListOut])
async def admin_list_refunds(
    db: DbDep, admin: AdminDep,
    kind: str = Query("all", description="all | refund | appeal"),
    status: str = Query("pending", description="all | pending"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """退款/申诉审核队列（默认只看待审）。"""
    data = await _refund_svc.list_reviews(
        db, kind=kind, status=status, skip=skip, limit=limit)
    return make_ok(data)


@router.post("/refunds/{refund_id}/review", response_model=None)
async def admin_review_refund(
    refund_id: uuid.UUID, body: RefundReviewRequest, db: DbDep, admin: AdminDep,
):
    """审核一条退款/申诉：approve 执行退款（dev-mock）/驳回。"""
    rec = await _refund_svc.review(
        db, admin, refund_id,
        approve=body.approve, amount_fen=body.amount_fen, reason=body.reason)
    await db.commit()
    return make_ok({"id": str(rec.id), "status": rec.status,
                    "state_code": rec.state_code, "amount_fen": rec.amount_fen})


@router.get("/orders/{order_id}/evidence", response_model=None)
async def admin_order_evidence(order_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """纠纷举证包（§4.6.4，结构化 JSON）。"""
    return make_ok(await _refund_svc.evidence_pack(db, order_id))


@router.post("/refunds/run-sla-alerts", response_model=None)
async def admin_run_refund_sla_alerts(db: DbDep, admin: AdminDep):
    """手动触发退款/申诉 SLA 超时告警（§4.5.3；也可由 cron 调用 CLI）。"""
    res = await _refund_svc.run_sla_alerts(db)
    await db.commit()
    return make_ok(res)


@router.get("/orders/{order_id}/evidence.html")
async def admin_order_evidence_html(order_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """举证包打印版 HTML（带时间戳水印，浏览器「打印为 PDF」即得举证 PDF）。"""
    from fastapi.responses import HTMLResponse
    html = await _refund_svc.evidence_html(db, order_id)
    return HTMLResponse(content=html)


# ── 收款主体管理（多主体/多渠道；不涉密）────────────────────────────────────
from app.services import payment_account_service as _pa_svc
from app.schemas.payments import (
    PaymentAccountItem, PaymentAccountCreate, PaymentAccountUpdate,
)


@router.get("/payment-accounts", response_model=BaseResponse[list[PaymentAccountItem]])
async def admin_list_payment_accounts(db: DbDep, admin: AdminDep):
    """收款主体列表（含密钥就绪布尔，绝不返回密钥）。"""
    return make_ok(await _pa_svc.admin_list(db))


@router.post("/payment-accounts", response_model=BaseResponse[PaymentAccountItem])
async def admin_create_payment_account(
    body: PaymentAccountCreate, db: DbDep, admin: AdminDep,
):
    acc = await _pa_svc.admin_create(
        db, name=body.name, subject_type=body.subject_type, provider=body.provider,
        config=body.config, secret_alias=body.secret_alias,
        branch_company_id=body.branch_company_id, is_active=body.is_active)
    await db.commit()
    return make_ok(_pa_svc._to_item(acc))


@router.put("/payment-accounts/{account_id}", response_model=BaseResponse[PaymentAccountItem])
async def admin_update_payment_account(
    account_id: uuid.UUID, body: PaymentAccountUpdate, db: DbDep, admin: AdminDep,
):
    acc = await _pa_svc.admin_update(db, account_id, fields=body.model_dump(exclude_unset=True))
    await db.commit()
    return make_ok(_pa_svc._to_item(acc))


@router.post("/payment-accounts/{account_id}/set-default", response_model=BaseResponse[PaymentAccountItem])
async def admin_set_default_payment_account(account_id: uuid.UUID, db: DbDep, admin: AdminDep):
    acc = await _pa_svc.set_default(db, account_id)
    await db.commit()
    return make_ok(_pa_svc._to_item(acc))


@router.post("/payment-accounts/{account_id}/toggle-active", response_model=BaseResponse[PaymentAccountItem])
async def admin_toggle_payment_account(account_id: uuid.UUID, db: DbDep, admin: AdminDep):
    acc = await _pa_svc.toggle_active(db, account_id)
    await db.commit()
    return make_ok(_pa_svc._to_item(acc))


@router.put("/payment-accounts/{account_id}/secrets", response_model=BaseResponse[PaymentAccountItem])
async def admin_set_payment_secrets(
    account_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep,
):
    """录入/更新该主体的渠道密钥（加密存库，明文不落库、接口不回传）。

    body = {密钥名: 值}；值为空字符串表示删除该密钥。
    """
    secrets = {str(k): ("" if v is None else str(v)) for k, v in (body or {}).items()}
    acc = await _pa_svc.set_secrets(db, account_id, secrets)
    await db.commit()
    return make_ok(_pa_svc._to_item(acc))


# ── 分公司管理 + 城市归属（阶段③：地方子公司）──────────────────────────────────
import datetime as _dt
from app.services import branch_service as _branch_svc


# ── 财务管理（§5.4）：营收统计 / 订单明细 / 导出 / 分成结算 ──────────────────────
import datetime as _fdt
from fastapi import Response as _Response
from app.services import finance_service as _fin_svc


def _period(month: str | None) -> tuple:
    """month=YYYY-MM；缺省=当月。返回 [start, end) 的 UTC datetime。"""
    today = _fdt.datetime.now(_fdt.timezone.utc)
    if month:
        y, m = (int(x) for x in month.split("-"))
    else:
        y, m = today.year, today.month
    start = _fdt.datetime(y, m, 1, tzinfo=_fdt.timezone.utc)
    end = _fdt.datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=_fdt.timezone.utc)
    return start, end


@router.get("/finance/summary", response_model=None)
async def admin_finance_summary(
    db: DbDep, admin: AdminDep,
    month: str = Query(None, description="YYYY-MM，缺省当月"),
    group_by: str = Query("account", description="account|branch|none"),
):
    start, end = _period(month)
    return make_ok(await _fin_svc.revenue_summary(db, start=start, end=end, group_by=group_by))


@router.get("/finance/orders", response_model=None)
async def admin_finance_orders(
    db: DbDep, admin: AdminDep, month: str = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
):
    start, end = _period(month)
    return make_ok(await _fin_svc.list_orders(db, start=start, end=end, skip=skip, limit=limit))


@router.get("/finance/export")
async def admin_finance_export(db: DbDep, admin: AdminDep, month: str = Query(None)):
    start, end = _period(month)
    csv_text = await _fin_svc.export_orders_csv(db, start=start, end=end)
    fname = f"orders_{(month or start.strftime('%Y-%m'))}.csv"
    # ﻿ BOM 让 Excel 正确识别 UTF-8 中文
    return _Response(
        content="﻿" + csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/finance/settlements", response_model=None)
async def admin_finance_settlements(db: DbDep, admin: AdminDep,
                                    branch_id: uuid.UUID = Query(None)):
    return make_ok(await _fin_svc.list_settlements(db, branch_id=branch_id))


@router.post("/finance/settlements/compute", response_model=None)
async def admin_finance_compute_settlement(body: dict, db: DbDep, admin: AdminDep):
    """计算（可落库）某分公司某周期分成。body={branch_id, start(YYYY-MM-DD), end, persist?}。"""
    b = (body or {})
    res = await _fin_svc.compute_settlement(
        db, branch_id=uuid.UUID(b["branch_id"]),
        start=_fdt.date.fromisoformat(b["start"]), end=_fdt.date.fromisoformat(b["end"]),
        persist=bool(b.get("persist")))
    await db.commit()
    return make_ok(res)


# ── 发票申请管理（§5.4）──────────────────────────────────────────────────────
from app.services import invoice_service as _inv_svc


@router.get("/invoices", response_model=None)
async def admin_list_invoices(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending", description="pending|issued|rejected|all"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _inv_svc.admin_list(db, status=status, skip=skip, limit=limit))


@router.post("/invoices/{invoice_id}/issue", response_model=None)
async def admin_issue_invoice(invoice_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """开具：回填发票号/链接，状态置 issued。body={invoice_no, invoice_url?}。"""
    rec = await _inv_svc.issue(
        db, invoice_id=invoice_id, admin_id=admin.id,
        invoice_no=(body or {}).get("invoice_no", ""), invoice_url=(body or {}).get("invoice_url"))
    await db.commit()
    return make_ok({"id": str(rec.id), "status": rec.status})


@router.post("/invoices/{invoice_id}/reject", response_model=None)
async def admin_reject_invoice(invoice_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    rec = await _inv_svc.reject(db, invoice_id=invoice_id, note=(body or {}).get("note"))
    await db.commit()
    return make_ok({"id": str(rec.id), "status": rec.status})


# ── 用户管理：封禁/解封（§5.3.1）────────────────────────────────────────────────
from app.services import user_admin_service as _user_svc


@router.get("/users", response_model=None)
async def admin_list_users(
    db: DbDep, admin: AdminDep,
    q: str = Query("", description="昵称/手机号/ID 搜索"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _user_svc.list_users(db, q=q, skip=skip, limit=limit))


@router.post("/users/{user_id}/ban", response_model=None)
async def admin_ban_user(user_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """封禁：body={reason, days?}；days 空=永久。"""
    days = (body or {}).get("days")
    u = await _user_svc.ban_user(
        db, user_id=user_id, reason=(body or {}).get("reason", ""),
        days=int(days) if days else None)
    await db.commit()
    return make_ok(_user_svc._to_item(u))


@router.post("/users/{user_id}/unban", response_model=None)
async def admin_unban_user(user_id: uuid.UUID, db: DbDep, admin: AdminDep):
    u = await _user_svc.unban_user(db, user_id=user_id)
    await db.commit()
    return make_ok(_user_svc._to_item(u))


# ── 内容质量反馈（§5.5）──────────────────────────────────────────────────────
from app.services import content_feedback_service as _cf_svc


@router.get("/content-feedback", response_model=None)
async def admin_list_content_feedback(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending"), target_type: str = Query("all"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _cf_svc.admin_list(db, status=status, target_type=target_type, skip=skip, limit=limit))


@router.post("/content-feedback/{feedback_id}/handle", response_model=None)
async def admin_handle_content_feedback(feedback_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """处理反馈：body={action: handled|dismissed, note?}。"""
    f = await _cf_svc.handle(db, feedback_id=feedback_id, admin_id=admin.id,
                             action=(body or {}).get("action", ""), note=(body or {}).get("note"))
    await db.commit()
    return make_ok({"id": str(f.id), "status": f.status})


# ── 封禁申诉审核（§5.3.1）──────────────────────────────────────────────────────
from app.services import ban_appeal_service as _appeal_svc


@router.get("/ban-appeals", response_model=None)
async def admin_list_ban_appeals(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending", description="pending|approved|rejected|all"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _appeal_svc.admin_list(db, status=status, skip=skip, limit=limit))


@router.post("/ban-appeals/{appeal_id}/review", response_model=None)
async def admin_review_ban_appeal(appeal_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """审核封禁申诉：approve=true 解封并补偿会员时长；false 维持封禁。body={approve, note?}。"""
    a = await _appeal_svc.review(
        db, appeal_id=appeal_id, admin_id=admin.id,
        approve=bool((body or {}).get("approve")), note=(body or {}).get("note"))
    await db.commit()
    return make_ok({"id": str(a.id), "status": a.status})


# ── 项目品牌（项目名）──────────────────────────────────────────────────────────
from app.services import branding_service as _branding_svc


@router.get("/branding", response_model=None)
async def admin_get_branding(db: DbDep, admin: AdminDep):
    return make_ok(await _branding_svc.get_branding(db))


@router.put("/branding", response_model=None)
async def admin_set_branding(body: dict, db: DbDep, admin: AdminDep):
    """改项目名/slogan（全前端启动读取，无需发版）。"""
    data = await _branding_svc.set_branding(
        db, app_name=(body or {}).get("app_name", ""),
        slogan=(body or {}).get("slogan"), updated_by=admin.id)
    await db.commit()
    return make_ok(data)


@router.get("/branch-companies", response_model=None)
async def admin_list_branches(db: DbDep, admin: AdminDep):
    """分公司列表（含城市归属 + 关联收款主体；银行账户不回明文）。"""
    return make_ok(await _branch_svc.list_branches(db))


@router.post("/branch-companies", response_model=None)
async def admin_create_branch(body: dict, db: DbDep, admin: AdminDep):
    b = await _branch_svc.create_branch(
        db, name=body["name"], contact_phone=body.get("contact_phone"),
        commission_rate=body.get("commission_rate"), legal_name=body.get("legal_name"),
        tax_number=body.get("tax_number"), bank_name=body.get("bank_name"),
        bank_account=body.get("bank_account"))
    await db.commit()
    return make_ok({"id": str(b.id)})


@router.put("/branch-companies/{branch_id}", response_model=None)
async def admin_update_branch(branch_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    await _branch_svc.update_branch(db, branch_id, fields=body or {})
    await db.commit()
    return make_ok({"ok": True})


@router.post("/branch-companies/{branch_id}/toggle-active", response_model=None)
async def admin_toggle_branch(branch_id: uuid.UUID, db: DbDep, admin: AdminDep):
    b = await _branch_svc.toggle_active(db, branch_id)
    await db.commit()
    return make_ok({"id": str(b.id), "is_active": b.is_active})


@router.post("/branch-companies/{branch_id}/cities", response_model=None)
async def admin_add_branch_city(branch_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    city_code = (body or {}).get("city_code")
    if not city_code:
        raise AppError(code=400, message="city_code 必填")
    eff = (body or {}).get("effective_from")
    eff_date = _dt.date.fromisoformat(eff) if eff else None
    c = await _branch_svc.add_city(db, branch_id, city_code=city_code, effective_from=eff_date)
    await db.commit()
    return make_ok({"id": str(c.id)})


@router.delete("/branch-companies/cities/{city_id}", response_model=None)
async def admin_remove_branch_city(city_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await _branch_svc.remove_city(db, city_id)
    await db.commit()
    return make_ok({"ok": True})


# ══ 客服与用户支持（§13）═════════════════════════════════════════════════════
from app.services import support_service as _support_svc
from app.services import faq_service as _faq_svc
from app.services import user_feedback_service as _ufb_svc


# ── 客服工单（§13.1）──────────────────────────────────────────────────────────
@router.get("/support/tickets", response_model=None)
async def admin_list_tickets(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending", description="pending|open|replied|closed|all"),
    category: str = Query("all"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _support_svc.admin_list(
        db, status=status, category=category, skip=skip, limit=limit))


@router.get("/support/tickets/{ticket_id}", response_model=None)
async def admin_ticket_thread(ticket_id: uuid.UUID, db: DbDep, admin: AdminDep):
    return make_ok(await _support_svc.get_thread(db, ticket_id=ticket_id))


@router.post("/support/tickets/{ticket_id}/reply", response_model=None)
async def admin_reply_ticket(ticket_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """客服回复。body={content}。"""
    m = await _support_svc.reply(
        db, ticket_id=ticket_id, sender_role="admin", sender_id=admin.id,
        content=(body or {}).get("content", ""))
    await db.commit()
    return make_ok({"id": str(m.id)})


@router.post("/support/tickets/{ticket_id}/close", response_model=None)
async def admin_close_ticket(ticket_id: uuid.UUID, db: DbDep, admin: AdminDep):
    t = await _support_svc.close_ticket(db, ticket_id=ticket_id, admin_id=admin.id)
    await db.commit()
    return make_ok({"id": str(t.id), "status": t.status})


# ── FAQ 维护（§13.2）──────────────────────────────────────────────────────────
@router.get("/faq", response_model=None)
async def admin_list_faq(db: DbDep, admin: AdminDep,
                         audience: str = Query("all"),
                         skip: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=500)):
    return make_ok(await _faq_svc.admin_list(db, audience=audience, skip=skip, limit=limit))


@router.post("/faq", response_model=None)
async def admin_create_faq(body: dict, db: DbDep, admin: AdminDep):
    """新增 FAQ。body={audience, category, question, answer, sort_order?}。"""
    f = await _faq_svc.create(
        db, admin_id=admin.id, audience=(body or {}).get("audience", "c"),
        category=(body or {}).get("category", "通用"),
        question=(body or {}).get("question", ""), answer=(body or {}).get("answer", ""),
        sort_order=(body or {}).get("sort_order", 0))
    await db.commit()
    return make_ok({"id": str(f.id)})


@router.put("/faq/{faq_id}", response_model=None)
async def admin_update_faq(faq_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    f = await _faq_svc.update(db, faq_id=faq_id, admin_id=admin.id, fields=(body or {}))
    await db.commit()
    return make_ok({"id": str(f.id)})


@router.delete("/faq/{faq_id}", response_model=None)
async def admin_delete_faq(faq_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await _faq_svc.delete(db, faq_id=faq_id)
    await db.commit()
    return make_ok({"ok": True})


# ── 意见反馈 / BUG（§13.3）────────────────────────────────────────────────────
@router.get("/feedback/suggestions", response_model=None)
async def admin_list_feedback(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending"), kind: str = Query("all"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    return make_ok(await _ufb_svc.admin_list(db, status=status, kind=kind, skip=skip, limit=limit))


@router.post("/feedback/suggestions/{feedback_id}/handle", response_model=None)
async def admin_handle_feedback(feedback_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """处理：body={action: reviewing|done|dismissed, note?}。"""
    f = await _ufb_svc.handle(db, feedback_id=feedback_id, admin_id=admin.id,
                              action=(body or {}).get("action", ""), note=(body or {}).get("note"))
    await db.commit()
    return make_ok({"id": str(f.id), "status": f.status})


# ══ 优惠券 / 兑换码（SP-4）═══════════════════════════════════════════════════
from app.services import coupon_service as _coupon_svc


@router.get("/coupons", response_model=None)
async def admin_list_coupons(db: DbDep, admin: AdminDep,
                             skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return make_ok(await _coupon_svc.admin_list(db, skip=skip, limit=limit))


@router.post("/coupons", response_model=None)
async def admin_create_coupon(body: dict, db: DbDep, admin: AdminDep):
    """建券。body={name, discount_type(amount|percent), discount_value, min_amount_fen?,
    max_discount_fen?, scope?, per_user_limit?, valid_days?, with_redeem_code?, redeem_quota?}。
    amount: discount_value=分; percent: discount_value=折扣率万分比(9000=9折)。"""
    b = body or {}
    c = await _coupon_svc.admin_create(
        db, admin_id=admin.id, name=b.get("name", ""),
        discount_type=b.get("discount_type", "amount"),
        discount_value=int(b.get("discount_value", 0)),
        min_amount_fen=int(b.get("min_amount_fen", 0) or 0),
        max_discount_fen=b.get("max_discount_fen"),
        scope=b.get("scope", "all"), per_user_limit=int(b.get("per_user_limit", 1) or 1),
        valid_days=b.get("valid_days"),
        with_redeem_code=bool(b.get("with_redeem_code", False)),
        redeem_quota=b.get("redeem_quota"))
    await db.commit()
    return make_ok({"id": str(c.id), "redeem_code": c.redeem_code})


@router.post("/coupons/{coupon_id}/active", response_model=None)
async def admin_set_coupon_active(coupon_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    c = await _coupon_svc.admin_set_active(
        db, coupon_id=coupon_id, is_active=bool((body or {}).get("is_active", True)))
    await db.commit()
    return make_ok({"id": str(c.id), "is_active": c.is_active})


@router.post("/coupons/{coupon_id}/grant", response_model=None)
async def admin_grant_coupon(coupon_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """直发给用户。body={user_ids:[uuid,...]}。"""
    uids = [uuid.UUID(x) for x in (body or {}).get("user_ids", [])]
    n = await _coupon_svc.admin_grant(db, coupon_id=coupon_id, user_ids=uids)
    await db.commit()
    return make_ok({"granted": n})


# ══ 敏感词库（§5.6）═══════════════════════════════════════════════════════════
from app.services import content_filter_service as _cf_filter


@router.get("/sensitive-words", response_model=None)
async def admin_list_sensitive_words(
    db: DbDep, admin: AdminDep,
    category: str = Query("all"), q: str | None = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
):
    return make_ok(await _cf_filter.admin_list(db, category=category, q=q, skip=skip, limit=limit))


@router.post("/sensitive-words", response_model=None)
async def admin_add_sensitive_word(body: dict, db: DbDep, admin: AdminDep):
    """新增敏感词。body={word, category?, action?}。"""
    s = await _cf_filter.admin_add(
        db, admin_id=admin.id, word=(body or {}).get("word", ""),
        category=(body or {}).get("category", "other"), action=(body or {}).get("action", "block"))
    await db.commit()
    return make_ok({"id": str(s.id)})


@router.post("/sensitive-words/batch", response_model=None)
async def admin_batch_add_sensitive_words(body: dict, db: DbDep, admin: AdminDep):
    """批量导入。body={words:[...], category?, action?}。"""
    n = await _cf_filter.admin_batch_add(
        db, admin_id=admin.id, words=(body or {}).get("words", []),
        category=(body or {}).get("category", "other"), action=(body or {}).get("action", "block"))
    await db.commit()
    return make_ok({"added": n})


@router.put("/sensitive-words/{word_id}", response_model=None)
async def admin_update_sensitive_word(word_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    s = await _cf_filter.admin_update(db, word_id=word_id, fields=(body or {}))
    await db.commit()
    return make_ok({"id": str(s.id), "is_active": s.is_active})


@router.delete("/sensitive-words/{word_id}", response_model=None)
async def admin_delete_sensitive_word(word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await _cf_filter.admin_delete(db, word_id=word_id)
    await db.commit()
    return make_ok({"ok": True})


# ══ 老师认证审核增强（§5.8）═══════════════════════════════════════════════════
@router.post("/teachers/{teacher_id}/claim", response_model=None)
async def admin_claim_teacher_cert(teacher_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """审核员认领认证任务（防多人同审）。"""
    t = await teacher_service.claim_cert(db, teacher_id=teacher_id, admin_id=admin.id)
    await db.commit()
    return make_ok({"teacher_id": str(t.id), "claimed_by": str(admin.id)})


@router.get("/teachers/cert-quality", response_model=None)
async def admin_teacher_cert_quality(db: DbDep, admin: AdminDep,
                                     days: int = Query(30, ge=1, le=365)):
    """认证审核质量监控：近 N 天申请量/通过率/驳回原因 Top5。"""
    return make_ok(await teacher_service.cert_quality(db, days=days))


# ══ 定价历史（§5.7）═══════════════════════════════════════════════════════════
@router.get("/pricing/history", response_model=None)
async def admin_pricing_history(db: DbDep, admin: AdminDep,
                                limit: int = Query(50, ge=1, le=200)):
    """学期定价变更历史（退款/争议举证）。"""
    return make_ok(await pricing_service.pricing_history(db, limit=limit))


# ══ 限时活动价 campaign（§5.7）═══════════════════════════════════════════════
from app.services import promo_service as _promo_svc
import datetime as _dt2


def _parse_dt(s: str):
    """ISO 字符串 → aware datetime（无时区按 UTC）。"""
    d = _dt2.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=_dt2.timezone.utc)


@router.get("/promo-campaigns", response_model=None)
async def admin_list_campaigns(db: DbDep, admin: AdminDep,
                               skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return make_ok(await _promo_svc.admin_list(db, skip=skip, limit=limit))


@router.post("/promo-campaigns", response_model=None)
async def admin_create_campaign(body: dict, db: DbDep, admin: AdminDep):
    """建活动。body={name, starts_at, ends_at, price_basic?, price_pro?, price_promax?,
    limit_type(none|once|total), total_quota?, is_promotional?}。价格为元/学期，留空=该档不参加。"""
    b = body or {}
    if not b.get("starts_at") or not b.get("ends_at"):
        raise AppError(code=400, message="开始/结束时间必填")
    c = await _promo_svc.admin_create(
        db, admin_id=admin.id, name=b.get("name", ""),
        starts_at=_parse_dt(b["starts_at"]), ends_at=_parse_dt(b["ends_at"]),
        price_basic=b.get("price_basic"), price_pro=b.get("price_pro"),
        price_promax=b.get("price_promax"), limit_type=b.get("limit_type", "none"),
        total_quota=b.get("total_quota"), is_promotional=bool(b.get("is_promotional", True)))
    await db.commit()
    return make_ok({"id": str(c.id)})


@router.post("/promo-campaigns/{campaign_id}/active", response_model=None)
async def admin_set_campaign_active(campaign_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    c = await _promo_svc.admin_set_active(
        db, campaign_id=campaign_id, is_active=bool((body or {}).get("is_active", True)))
    await db.commit()
    return make_ok({"id": str(c.id), "is_active": c.is_active})


# ══ 公告管理（§5.6）═══════════════════════════════════════════════════════════
from app.services import announcement_service as _ann_svc


@router.get("/announcements", response_model=None)
async def admin_list_announcements(db: DbDep, admin: AdminDep,
                                   skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return make_ok(await _ann_svc.admin_list(db, skip=skip, limit=limit))


@router.post("/announcements", response_model=None)
async def admin_create_announcement(body: dict, db: DbDep, admin: AdminDep):
    """发布公告。body={title, content, audience(all|institution|grade), target_values?[],
    pinned?, starts_at?, ends_at?}。定向公告需填 target_values（机构id 或 年级名）。"""
    b = body or {}
    sa_dt = _parse_dt(b["starts_at"]) if b.get("starts_at") else None
    ea_dt = _parse_dt(b["ends_at"]) if b.get("ends_at") else None
    a = await _ann_svc.admin_create(
        db, admin_id=admin.id, title=b.get("title", ""), content=b.get("content", ""),
        audience=b.get("audience", "all"), target_values=b.get("target_values"),
        pinned=bool(b.get("pinned", False)), starts_at=sa_dt, ends_at=ea_dt)
    await db.commit()
    return make_ok({"id": str(a.id)})


@router.put("/announcements/{ann_id}", response_model=None)
async def admin_update_announcement(ann_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    a = await _ann_svc.admin_update(db, ann_id=ann_id, fields=(body or {}))
    await db.commit()
    return make_ok({"id": str(a.id), "is_active": a.is_active})


@router.delete("/announcements/{ann_id}", response_model=None)
async def admin_delete_announcement(ann_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await _ann_svc.admin_delete(db, ann_id=ann_id)
    await db.commit()
    return make_ok({"ok": True})


# ══ 老师月度限额配置（§5.6）═══════════════════════════════════════════════════
from app.services import teacher_limit_service as _tl_svc


@router.get("/teacher-limits", response_model=None)
async def admin_get_teacher_limits(db: DbDep, admin: AdminDep):
    """全局老师限额默认配置。"""
    return make_ok(await _tl_svc.get_limits(db))


@router.put("/teacher-limits", response_model=None)
async def admin_update_teacher_limits(body: dict, db: DbDep, admin: AdminDep):
    """改全局默认。body 可含 max_students/monthly_paper_quota/monthly_grading_quota/
    warn_threshold_pct/reset_day。次月（按 reset_day）起按新值计。"""
    res = await _tl_svc.update_limits(db, fields=(body or {}), admin_id=admin.id)
    await db.commit()
    return make_ok(res)


@router.post("/teachers/{teacher_id}/limits", response_model=None)
async def admin_set_teacher_override(teacher_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """设单个老师的额度覆盖（字段省略/传 null=随全局）。"""
    t = await _tl_svc.set_teacher_override(db, teacher_id=teacher_id, fields=(body or {}))
    await db.commit()
    return make_ok({
        "teacher_id": str(t.id), "max_students": t.max_students,
        "monthly_paper_quota": t.monthly_paper_quota,
        "monthly_grading_quota": t.monthly_grading_quota,
    })


# ══ 学习信息变更月度上限（§5.6）═══════════════════════════════════════════════
from app.services import info_change_service as _ic_svc


@router.get("/info-change-limit", response_model=None)
async def admin_get_info_change_limit(db: DbDep, admin: AdminDep):
    return make_ok({"limit": await _ic_svc.get_limit(db)})


@router.put("/info-change-limit", response_model=None)
async def admin_set_info_change_limit(body: dict, db: DbDep, admin: AdminDep):
    """改学习信息（年级/教材/学期）月度变更上限。body={limit}。次月起按新值计。"""
    v = await _ic_svc.set_limit(db, value=int((body or {}).get("limit", 3)), admin_id=admin.id)
    await db.commit()
    return make_ok({"limit": v})


# ══ 机构套餐配置（§9.1/§5.6，全配置驱动）═════════════════════════════════════
from app.services import institution_package_service as _pkg_svc


@router.get("/institution-packages", response_model=None)
async def admin_get_institution_packages(db: DbDep, admin: AdminDep):
    """套餐档位 + 各档配额 + 预警/重置日（全局配置）。"""
    return make_ok(await _pkg_svc.get_config(db))


@router.put("/institution-packages", response_model=None)
async def admin_update_institution_packages(body: dict, db: DbDep, admin: AdminDep):
    """改套餐配置。body={tiers:[{key,name,teacher_seats,paper_pool,grading_pool}...],
    warn_threshold_pct, reset_day}。可增删档位，不发版。"""
    res = await _pkg_svc.update_config(db, config=(body or {}), admin_id=admin.id)
    await db.commit()
    return make_ok(res)


@router.post("/institutions/{institution_id}/package", response_model=None)
async def admin_set_institution_package(institution_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """给机构指定套餐 + 可选覆盖。body={package_tier(null=取消), teacher_seats_override?,
    paper_pool_override?, grading_pool_override?}。"""
    b = body or {}
    inst = await _pkg_svc.set_institution_package(
        db, institution_id=institution_id, package_tier=b.get("package_tier"),
        overrides={k: b[k] for k in ("teacher_seats_override", "paper_pool_override",
                                     "grading_pool_override") if k in b})
    await db.commit()
    return make_ok({"id": str(inst.id), "package_tier": inst.package_tier})


@router.get("/institutions/{institution_id}/package-usage", response_model=None)
async def admin_institution_package_usage(institution_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """某机构套餐 + 池用量（超管查看）。"""
    return make_ok(await _pkg_svc.usage_overview(db, institution_id=institution_id))
