"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from pydantic import BaseModel
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, require_role
from app.models.d1_users import User
from app.schemas.auth import AdminLoginRequest, TokenResponse
from app.models.d5_learning import VocabularyWord
from app.models.d12_v2_exams import SimulatedQuestion
from app.schemas.admin import AdminOverviewOut
from app.schemas.base import BaseResponse, make_ok
from app.api.v1.upload import PresignRequest, PresignOut
from app.schemas.questions import (
    AdminQuestionItem,
    AdminQuestionListOut,
    QuestionReviewRequest,
)
from app.schemas.semesters import SemesterPricing, SemesterPricingUpdate
from app.schemas.curriculum import UnitDeleteIn
from app.schemas.sales_crm import (
    SalesLeadCreate, SalesLeadUpdate, SalesLeadImport, SalesLeadIngest,
    BaiduAkIn, BaiduFetchIn, ActivityCreate,
    SalesLeadOut, ActivityOut, CallRecordIn, AnalyzeTextIn, BatchAssignIn, MergeLeadsIn,
    AutoAssignIn, SalesConfigUpdate, ScriptsIn,
    WecomIngestIn, WecomConfigUpdate, WecomMsgOut,
)
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
    InstitutionCodePricing,
    InstitutionCodePricingUpdate,
)
from app.schemas.kp import (
    ApproveCandidateRequest,
    KpCandidateItem,
    KpCandidateListOut,
    KpNodeItem,
    KpNodeListOut,
    KpNodeOverviewItem,
    KpNodeOverviewOut,
    KpNodeDetailOut,
    UpdateNodeIn,
    NodeTreeItem,
    NodeTreeOut,
    CreateNodeIn,
    MoveNodeIn,
    MergeCandidateRequest,
    RejectCandidateRequest,
    UnitExtractOut,
    UnitNodeItem,
    UnitNodeListOut,
    PlatformQuestionItem,
    PlatformQuestionListOut,
    GenSimOut,
    RealQuestionIn,
    RealQuestionBulkIn,
    RealImportItemOut,
    RealImportBulkOut,
    PaperListItem,
    PaperListOut,
    PaperQuestionItem,
    PaperDetailOut,
    QuestionKpRef,
    AttachKpIn,
    KpBulkAttachIn,
    SectionKpIn,
    PaperDeleteIn,
    SuggestKpItem,
    SuggestKpOut,
    SuggestKpIn,
    KpPromptItem,
    KpPromptsIn,
    KpPromptsOut,
    SuggestTextIn,
    GenSimBulkIn,
    ReviewBulkIn,
    GenSimBulkOut,
    RealExtractCreatedOut,
    RealExtractJobOut,
    ParsedRealQuestion,
    RegionIn,
    RegionRename,
    RegionItem,
    ReviewRequest,
    VocabListCreate,
    VocabListOut,
    VocabListsOut,
    VocabItemsIn,
    VocabItemOut,
    VocabItemsOut,
    NodeResourceItem,
    NodeResourceListOut,
    UnitContentOverviewOut,
    UnitPublishOut,
    VersionDiffOut,
    VersionItem,
    VersionListOut,
    AddResourceIn,
    UpdateResourceIn,
    LSAdminItem,
    LSAdminListOut,
    LSExtractIn,
    LSExtractOut,
    LSConfigOut,
    LSConfigIn,
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


# ─── 知识点内容审核/编辑 ───────────────────────────────────────────────────────
# 已退役:旧 /contents(knowledge_point_contents)审核改由 /node-resources(node_resource lecture)统一承接。


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


@router.get("/knowledge-nodes", response_model=BaseResponse[KpNodeOverviewOut])
async def knowledge_nodes_overview_api(
    db: DbDep, admin: AdminDep,
    axis: str | None = None, stage: str | None = None, status: str | None = None,
    q: str | None = None, skip: int = 0, limit: int = 30,
):
    """知识图谱总览(D1):节点分页 + 每节点完整度/引用计数。status 空=全部。"""
    items, total = await kp_candidate_service.list_nodes_overview(
        db, axis=axis, stage=stage, status=status or None, q=q, skip=skip, limit=limit)
    return make_ok(KpNodeOverviewOut(total=total, items=[KpNodeOverviewItem(**it) for it in items]))


@router.get("/knowledge-nodes/tree", response_model=BaseResponse[NodeTreeOut])
async def knowledge_node_tree_api(db: DbDep, admin: AdminDep, axis: str | None = None,
                                  with_counts: bool = False, stage: str | None = None):
    """受控知识树(E1):嵌套结构。with_counts=true 每节点带教材/真题挂载数;stage 按学段过滤。"""
    items = await kp_candidate_service.node_tree(db, axis=axis, with_counts=with_counts, stage=stage)
    return make_ok(NodeTreeOut(items=[NodeTreeItem(**it) for it in items]))


@router.post("/knowledge-nodes", response_model=BaseResponse[dict])
async def create_knowledge_node_api(body: CreateNodeIn, db: DbDep, admin: AdminDep):
    """在树上手建节点(有 parent 继承轴;否则需 axis)。"""
    n = await kp_candidate_service.create_node(
        db, name=body.name, parent_id=body.parent_id, axis=body.axis,
        node_kind=body.node_kind, applicable_stages=body.applicable_stages)
    await db.commit()
    return make_ok({"id": str(n.id), "code": n.code, "name": n.name})


@router.get("/textbook-word-stats", response_model=BaseResponse[dict])
async def textbook_word_stats_api(db: DbDep, admin: AdminDep,
                                  textbook: str | None = None, grade: str | None = None):
    """教材高频词统计:某教材版+年级下每个词出现在多少单元(出现单元数=教材内词频)。"""
    from app.services import curriculum_service as cs
    return make_ok(await cs.textbook_word_stats(db, textbook=textbook, grade=grade))


@router.get("/kp-exam-stats", response_model=BaseResponse[dict])
async def kp_exam_stats_api(db: DbDep, admin: AdminDep, grp: str | None = None,
                           textbook: str | None = None, stage: str | None = None,
                           grade: str | None = None, region_code: str | None = None,
                           exam_type: str | None = None):
    """按考点统计已挂真题的考试类型分布;支持 教材版/学段/年级/地区/考试类型 多维筛选。"""
    return make_ok(await kp_candidate_service.exam_type_stats(
        db, grp=grp, textbook=textbook, stage=stage, grade=grade,
        region_code=region_code, exam_type=exam_type))


@router.get("/lecture-nodes", response_model=BaseResponse[dict])
async def list_lecture_nodes_api(db: DbDep, admin: AdminDep,
                                 grp: str | None = None, skip: int = 0, limit: int = 20):
    """有详解的考点列表(供「详解拆分审核」页)。grp=词法/句法 可筛。"""
    from app.services import kp_split_service as kss2
    items, total = await kss2.list_lecture_nodes(db, grp=grp, skip=skip, limit=limit)
    return make_ok({"items": [{**it, "id": str(it["id"])} for it in items], "total": total})


@router.post("/knowledge-nodes/{node_id}/split-lecture", response_model=BaseResponse[dict])
async def split_lecture_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """AI 把该考点的详解拆成若干子考点(只返回建议名,不建节点;人工确认后再建)。"""
    from app.services import kp_split_service as kss2
    return make_ok(await kss2.split_lecture(db, node_id))


@router.post("/knowledge-nodes/{node_id}/move", response_model=BaseResponse[dict])
async def move_knowledge_node_api(node_id: uuid.UUID, body: MoveNodeIn, db: DbDep, admin: AdminDep):
    """移动节点(改 parent;parent_id 省略=升为顶层)。禁跨轴/成环。"""
    n = await kp_candidate_service.set_parent(db, node_id=node_id, parent_id=body.parent_id)
    await db.commit()
    return make_ok({"id": str(n.id), "parent_id": str(n.parent_id) if n.parent_id else None})


@router.get("/knowledge-nodes/{node_id}", response_model=BaseResponse[KpNodeDetailOut])
async def knowledge_node_detail_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """节点详情(D2):别名 / 引用单元 / 引用真题 / 六维完整度 / 学生掌握分布。"""
    return make_ok(KpNodeDetailOut(**(await kp_candidate_service.node_detail(db, node_id=node_id))))


@router.get("/knowledge-nodes/{node_id}/hub", response_model=BaseResponse[dict])
async def knowledge_node_hub_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """知识点详情枢纽(F):详解正文 + 反向关联(教材/真题/仿真)+ 关系边。"""
    return make_ok(await kp_candidate_service.node_hub(db, node_id=node_id))


@router.patch("/knowledge-nodes/{node_id}", response_model=BaseResponse[KpNodeDetailOut])
async def update_knowledge_node_api(node_id: uuid.UUID, body: UpdateNodeIn, db: DbDep, admin: AdminDep):
    """改节点:名称 / 子类型 / 适用学段 / 描述。"""
    await kp_candidate_service.update_node(
        db, node_id=node_id, name=body.name, node_kind=body.node_kind,
        applicable_stages=body.applicable_stages, description=body.description)
    await db.commit()
    return make_ok(KpNodeDetailOut(**(await kp_candidate_service.node_detail(db, node_id=node_id))))


@router.post("/knowledge-nodes/{node_id}/retire", response_model=BaseResponse[dict])
async def retire_knowledge_node_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """停用节点(status=retired,不硬删;学生/真题引用保留)。"""
    n = await kp_candidate_service.set_node_status(db, node_id=node_id, status="retired")
    await db.commit()
    return make_ok({"id": str(n.id), "status": n.status})


@router.get("/knowledge-nodes/{node_id}/children", response_model=BaseResponse[list[dict]])
async def list_node_children_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """某节点的直接子节点列表(供「编辑子考点」弹框:改名/删除)。"""
    return make_ok(await kp_candidate_service.list_children(db, node_id=node_id))


@router.delete("/knowledge-nodes/{node_id}", response_model=BaseResponse[dict])
async def delete_knowledge_node_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """硬删除节点(连带其挂边)。有子节点则拒绝;不动共享词汇/题目主表。不可恢复,慎用。"""
    r = await kp_candidate_service.delete_node(db, node_id=node_id)
    await db.commit()
    return make_ok(r)


@router.post("/knowledge-nodes/{node_id}/restore", response_model=BaseResponse[dict])
async def restore_knowledge_node_api(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """恢复节点(status=active)。"""
    n = await kp_candidate_service.set_node_status(db, node_id=node_id, status="active")
    await db.commit()
    return make_ok({"id": str(n.id), "status": n.status})


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


# ─── 机构激活码定价配置（分 / 月）─────────────────────────────────────────────

@router.get("/institution-code-pricing", response_model=BaseResponse[InstitutionCodePricing])
async def get_institution_code_pricing(db: DbDep, admin: AdminDep):
    """读机构激活码档位定价（basic/pro/promax 分 / 月）。"""
    return make_ok(await pricing_service.get_institution_code_pricing(db))


@router.put("/institution-code-pricing", response_model=BaseResponse[InstitutionCodePricing])
async def update_institution_code_pricing(
    body: InstitutionCodePricingUpdate, db: DbDep, admin: AdminDep
):
    """运营改机构激活码定价（三档单价，正整数，分 / 月）。"""
    updated = await pricing_service.update_institution_code_pricing(
        db, pricing=InstitutionCodePricing(
            basic=body.basic, pro=body.pro, promax=body.promax),
        updated_by=admin.id,
    )
    await db.commit()
    return make_ok(updated)


@router.get("/institution-code-pricing/history", response_model=BaseResponse[list[dict]])
async def institution_code_pricing_history(db: DbDep, admin: AdminDep, limit: int = 50):
    """机构激活码定价变更历史（倒序）。"""
    return make_ok(await pricing_service.institution_code_pricing_history(db, limit=limit))


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


class LlmModelConfig(BaseModel):
    model: str                              # 生效模型名
    presets: list[str] = []                 # 常见模型建议(下拉)
    available: list[str] = []               # 厂商当前真实可用模型(GET /models;空=无法确定)
    base_url: str = ""                      # 当前 endpoint(只读,改 .env)
    dev_mock: bool = False                  # 是否 dev-mock(api_key 为 placeholder)


@router.get("/llm-config", response_model=BaseResponse[LlmModelConfig])
async def get_llm_config(db: DbDep, admin: AdminDep):
    """读 LLM 生效模型配置 + 厂商当前可用模型列表(模型名可改;base_url / api_key 仍走 .env)。"""
    from app.core.config import settings
    from app.services import llm_config_service
    from app.services.llm_provider import is_llm_dev_mode, list_models
    return make_ok(LlmModelConfig(
        model=await llm_config_service.get_model(db),
        presets=llm_config_service.PRESET_MODELS,
        available=await list_models(),
        base_url=settings.llm_base_url, dev_mock=is_llm_dev_mode()))


@router.put("/llm-config", response_model=BaseResponse[LlmModelConfig])
async def update_llm_config(body: LlmModelConfig, db: DbDep, admin: AdminDep):
    """改 LLM 生效模型。保存前用 /models 校验:模型不在厂商当前可用列表则拒绝(防用到已下线/拼错的模型)。"""
    from app.core.config import settings
    from app.services import llm_config_service
    from app.services.llm_provider import is_llm_dev_mode, list_models
    avail = await list_models()
    if avail and body.model not in avail:   # 仅当成功取到列表才校验,取不到不锁死
        raise AppError(code=400, message=f"模型「{body.model}」不在厂商当前可用列表,请选用:{', '.join(avail)}")
    model = await llm_config_service.set_model(db, model=body.model, updated_by=admin.id)
    await db.commit()
    return make_ok(LlmModelConfig(
        model=model, presets=llm_config_service.PRESET_MODELS,
        available=avail, base_url=settings.llm_base_url, dev_mock=is_llm_dev_mode()))


@router.get("/llm-usage", response_model=BaseResponse[dict])
async def get_llm_usage(db: DbDep, admin: AdminDep, days: int = 30):
    """LLM 用量与成本估算:近 days 天总量 + 按用途/模型/天。成本为估算(按价目表)。"""
    from app.services import usage_log_service
    return make_ok(await usage_log_service.summary(db, days=max(1, min(days, 365))))


# ─── R10 语法掌握/定级:参数配置 + 探针离线预生成 ──────────────────────────
@router.get("/grammar-config", response_model=BaseResponse[dict])
async def get_grammar_config(db: DbDep, admin: AdminDep):
    """读语法掌握/定级运营参数(阈值/复测/分级/纸质权重),含默认值供参照。"""
    from app.services import grammar_config_service
    return make_ok({"config": await grammar_config_service.get_config(db),
                    "defaults": grammar_config_service.DEFAULTS})


@router.put("/grammar-config", response_model=BaseResponse[dict])
async def update_grammar_config(body: dict, db: DbDep, admin: AdminDep):
    """改语法掌握/定级运营参数(只接受已知键),即时生效。"""
    from app.services import grammar_config_service
    cfg = await grammar_config_service.update_config(db, patch=body or {}, updated_by=admin.id)
    await db.commit()
    return make_ok({"config": cfg})


@router.post("/grammar/probe-backfill", response_model=BaseResponse[dict])
async def backfill_grammar_probes_api(db: DbDep, admin: AdminDep, limit: int = 50,
                                      only_missing: bool = True, max_tokens_budget: int = 200000):
    """R10.8 批量给语法点生成「理解探针库」(grammar_probes_json),带 token 预算熔断。"""
    from app.services import grammar_probe_service as gps
    r = await gps.backfill_probes(db, limit=limit, only_missing=only_missing,
                                  max_tokens_budget=max_tokens_budget)
    return make_ok(r)


@router.get("/grammar/calibration", response_model=BaseResponse[dict])
async def grammar_calibration(db: DbDep, admin: AdminDep, student_id: str | None = None):
    """R10 验证闭环:用真实作答核对「已掌握」判定准不准(false_mastery_rate 高=虚高)。"""
    from app.services import grammar_eval_service
    sid = None
    if student_id:
        import uuid as _uuid
        try:
            sid = _uuid.UUID(student_id)
        except (ValueError, TypeError):
            raise AppError(code=400, message="student_id 非法")
    return make_ok(await grammar_eval_service.calibration_report(db, student_id=sid))


@router.get("/llm-balance", response_model=BaseResponse[dict])
async def get_llm_balance(admin: AdminDep):
    """DeepSeek 账户真实余额(只读)。dev-mock / 非 DeepSeek 厂商返回 ok=false。"""
    from app.services import usage_log_service
    return make_ok(await usage_log_service.fetch_balance())


@router.post("/vocab/probe-backfill", response_model=BaseResponse[dict])
async def backfill_vocab_probes_api(db: DbDep, admin: AdminDep, limit: int = 50,
                                    only_missing: bool = True, max_tokens_budget: int = 200000):
    """R9.1 批量给词典词生成「理解探针库」(probes_json),带 token 预算熔断。
    返回 {scanned, filled, stopped, spent_tokens}。"""
    from app.services import vocab_probe_service as vps
    r = await vps.backfill_probes(db, limit=limit, only_missing=only_missing,
                                  max_tokens_budget=max_tokens_budget)
    return make_ok(r)


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


@router.get("/institutions", response_model=BaseResponse[dict])
async def admin_list_institutions(
    db: DbDep, admin: AdminDep, status: str | None = None, source: str | None = None,
    skip: int = 0, limit: int = 50,
):
    rows, total = await admin_institution_service.list_institutions(
        db, status=status, source=source, skip=skip, limit=limit)
    return make_ok({"total": total, "items": [AdminInstitutionOut.model_validate(i).model_dump() for i in rows]})


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
async def list_curriculum_units(
    db: DbDep, admin: AdminDep,
    textbook_version: str | None = None, grade: str | None = None,
    semester: str | None = None, skip: int = 0, limit: int = 50,
):
    """课程单元 + 内容完成度统计(服务端筛选 + 分页),供 Admin 内容生成触发。

    返回 {total, items, options};options 为全量去重的教材/年级/学期下拉,供分页后前端仍能筛选。
    """
    stats, total = await curriculum_service.list_units_with_stats(
        db, textbook_version=textbook_version, grade=grade,
        semester=semester, skip=skip, limit=limit)
    options = await curriculum_service.unit_filter_options(db)
    return make_ok({
        "total": total,
        "options": options,
        "items": [
            {
                "unit_id": str(s.unit_id),
                "textbook_version": s.textbook_version,
                "grade": s.grade,
                "semester": s.semester,
                "unit_no": s.unit_no,
                "unit_title": s.unit_title,
                "kp_count": s.kp_count,
                "content_count": s.content_count,
                "passage_count": s.passage_count,
                "word_count": s.word_count,
                "content_rate": s.content_rate,
                "unit_pdf_url": s.unit_pdf_url,
            }
            for s in stats
        ],
    })


@router.post("/curriculum/units/delete", response_model=BaseResponse[dict])
async def delete_curriculum_units_api(body: UnitDeleteIn, db: DbDep, admin: AdminDep):
    """批量删除单元(连带知识图谱边 unit_node/unit_knowledge_points、短文及其考点边、
    单词通词表 curriculum_words;AI 练习题解联保留)。仅删关联,不动共享的节点/词汇主表。"""
    n = await curriculum_service.delete_units(db, unit_ids=body.unit_ids)
    await db.commit()
    return make_ok({"deleted": n})


@router.post("/curriculum/units/{unit_id}/generate")
async def generate_unit_content(
    unit_id: uuid.UUID,
    db: DbDep,
    admin: AdminDep,
):
    """触发 AI 生成指定单元的课程内容（dev mock 即时；生产约 5-15s）。

    KP-First:内容直写 node_resource(lecture,挂命中 node),status='draft',
    需在 NodeResources 后台页审核发布后学生才可见;未命中 node 的 KP 落候选,审核合并后可重生。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.services import curriculum_ai_service

    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="单元不存在")

    # 有 PDF 原文 → 用原文生成(更准)并析出短文;否则按教材元信息生成(无短文)
    if unit.source_text:
        ai_unit = await curriculum_ai_service.generate_unit_from_text(
            textbook_version=unit.textbook_version, grade=str(unit.grade),
            semester=str(unit.semester), unit_no=unit.unit_no,
            unit_text=unit.source_text, detected_title=unit.unit_title)
    else:
        ai_unit = await curriculum_ai_service.generate_unit(
            textbook_version=unit.textbook_version, grade=str(unit.grade),
            semester=str(unit.semester), unit_no=unit.unit_no)
    await curriculum_service.persist_unit(db, ai_unit=ai_unit, content_status="draft")
    # R1:生成后自动对齐知识图谱(防御式,失败不阻断生成)
    from app.services import curriculum_kp_service
    await curriculum_kp_service.extract_for_ai_unit(db, unit_id=unit_id, ai_unit=ai_unit)
    # 有原文 → 析出短文(听力/阅读/写作)
    if unit.source_text:
        try:
            passages = await curriculum_ai_service.extract_unit_passages(unit.source_text)
            if passages:
                await curriculum_service.persist_unit_passages(db, unit_id=unit_id, passages=passages)
        except Exception:  # noqa: BLE001
            pass
    await db.commit()

    # 返回更新后的统计(按本单元所在教材/年级/学期取,单学期单元数少)
    stats, _ = await curriculum_service.list_units_with_stats(
        db, textbook_version=unit.textbook_version, grade=str(unit.grade),
        semester=str(unit.semester), limit=200)
    stat = next((s for s in stats if s.unit_id == unit_id), None)
    return make_ok({
        "unit_id": str(unit_id),
        "kp_count": stat.kp_count if stat else 0,
        "content_count": stat.content_count if stat else 0,
        "content_rate": stat.content_rate if stat else 0.0,
    })


# ─── 单元 ↔ 知识图谱节点（R1 教材接入）─────────────────────────────────────────

@router.get("/curriculum/units/{unit_id}/passages", response_model=BaseResponse[dict])
async def list_unit_passages_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """该单元析出的短文(听力脚本/阅读短文/写作范文)+ 每篇已关联的考点。"""
    import sqlalchemy as _sa
    from app.models.d4_knowledge import CurriculumUnitPassage as _P, UnitPassageKp as _PK
    from app.models.d15_knowledge_graph import KnowledgeNode as _N
    rows = (await db.execute(_sa.select(_P).where(_P.unit_id == unit_id)
                             .order_by(_P.kind, _P.sort_order))).scalars().all()
    pids = [p.id for p in rows]
    kps: dict = {}
    if pids:
        for pid, nid, nm, code in (await db.execute(
            _sa.select(_PK.passage_id, _N.id, _N.name, _N.code)
            .join(_N, _N.id == _PK.node_id).where(_PK.passage_id.in_(pids)))).all():
            kps.setdefault(pid, []).append({"node_id": str(nid), "name": nm, "code": code})
    return make_ok({"total": len(rows), "items": [
        {"id": str(p.id), "unit_id": str(p.unit_id), "kind": p.kind,
         "title": p.title, "text": p.text, "sort_order": p.sort_order,
         "kps": kps.get(p.id, [])} for p in rows]})


@router.get("/curriculum/units/{unit_id}/pdf")
async def get_unit_pdf_proxy(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """同源代理单元 PDF:服务端从 COS 取字节回传(inline)。

    前端用 authed XHR 取回再转 blob: URL 内嵌预览——绕开「跨域 PDF 在 iframe 里不渲染、
    但新标签能开」的 Chrome 行为。返回原始 PDF 字节,非 JSON 信封。
    """
    from fastapi import Response
    from app.models.d4_knowledge import CurriculumUnit
    import httpx
    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id))).scalar_one_or_none()
    if unit is None or not (unit.unit_pdf_url or "").strip():
        raise AppError(code=404, message="该单元无 PDF")
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(unit.unit_pdf_url)
            r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise AppError(code=502, message=f"取单元 PDF 失败:{exc}")
    return Response(content=r.content, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=unit.pdf",
                             "Cache-Control": "private, max-age=300"})


@router.post("/curriculum/units/{unit_id}/passages/generate", response_model=BaseResponse[dict])
async def generate_unit_passages_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """从单元原文(source_text,来自上传 PDF)AI 析出 听力/阅读/写作 短文,整体覆盖旧短文。

    标题与原文按教材**原样抽取**(不改写/不翻译),与 PDF 保持一致。无原文则报错提示先拆 PDF。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.services import curriculum_ai_service
    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id))).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="单元不存在")
    src = (unit.source_text or "").strip()
    if not src:
        # 无原文 → 回退:用该单元已挂的 PDF(unit_pdf_url)抽文字;扫描件(无文字层)自动走 OCR
        if not (unit.unit_pdf_url or "").strip():
            raise AppError(code=400, message="该单元无原文也无 PDF,无法析出短文(请先在批量上传里拆出该单元 PDF)")
        try:
            src = (await pdf_upload_service.fetch_pdf_text(
                unit.unit_pdf_url, ocr_fallback=True)).strip()
        except Exception as exc:  # noqa: BLE001
            raise AppError(code=400, message=f"从该单元 PDF 回取文字失败:{exc}")
        if not src:
            raise AppError(code=400, message="该单元 PDF 无文字层、OCR 也未识别到文字(或 OCR 未配置),无法析出短文")
        unit.source_text = src   # 回存(含 OCR 结果),下次直接用,免再下载/识别
    passages = await curriculum_ai_service.extract_unit_passages(src)
    n = await curriculum_service.persist_unit_passages(db, unit_id=unit_id, passages=passages)
    await db.commit()
    # 复用 list 查询返回最新短文(含每篇 kps),前端直接刷新
    out = await list_unit_passages_api(unit_id, db, admin)
    out.data["generated"] = n
    return out


async def _resolve_unit_source_text(db, unit) -> str:
    """取单元原文:优先 source_text;无则回退该单元 PDF 抽文字(扫描件走 OCR),并回存。"""
    src = (unit.source_text or "").strip()
    if src:
        return src
    if not (unit.unit_pdf_url or "").strip():
        raise AppError(code=400, message="该单元无原文也无 PDF(请先在批量上传里拆出该单元 PDF)")
    try:
        src = (await pdf_upload_service.fetch_pdf_text(unit.unit_pdf_url, ocr_fallback=True)).strip()
    except Exception as exc:  # noqa: BLE001
        raise AppError(code=400, message=f"从该单元 PDF 回取文字失败:{exc}")
    if not src:
        raise AppError(code=400, message="该单元 PDF 无文字层、OCR 也未识别到文字(或 OCR 未配置)")
    unit.source_text = src
    return src


async def _unit_structured_out(db, unit_id: uuid.UUID) -> dict:
    """读单元结构化解析,组装成 {grammar:[], listening:[], writing:{}}。"""
    import sqlalchemy as _sa
    from app.models.d22_unit_structured import UnitSection as _S, UnitSectionSentence as _SS
    from app.models.d15_knowledge_graph import KnowledgeNode as _KN
    secs = (await db.execute(_sa.select(_S).where(_S.unit_id == unit_id)
                             .order_by(_S.kind, _S.sort_order))).scalars().all()
    sids = [s.id for s in secs]
    sent_map: dict = {}
    if sids:
        for r in (await db.execute(_sa.select(_SS).where(_SS.section_id.in_(sids))
                                   .order_by(_SS.sort_order))).scalars().all():
            sent_map.setdefault(r.section_id, []).append(
                {"id": str(r.id), "text": r.text, "difficulty": r.difficulty,
                 "syntax_points": r.syntax_points or []})
    # 已关联节点 → 取中文名
    node_ids = [s.node_id for s in secs if s.node_id]
    name_map: dict = {}
    if node_ids:
        name_map = dict((await db.execute(
            _sa.select(_KN.id, _KN.name).where(_KN.id.in_(node_ids)))).all())
    out: dict = {"grammar": [], "listening": [], "writing": None}
    for s in secs:
        if s.kind == "writing":
            out["writing"] = {"id": str(s.id), "requirement": s.requirement, "body_text": s.body_text}
            continue
        out.setdefault(s.kind, []).append({
            "id": str(s.id), "point_name": s.point_name,
            "node_id": str(s.node_id) if s.node_id else None, "node_code": s.node_code,
            "node_name": name_map.get(s.node_id) if s.node_id else None,
            "sentences": sent_map.get(s.id, [])})
    return out


@router.get("/curriculum/units/{unit_id}/structured", response_model=BaseResponse[dict])
async def get_unit_structured_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """单元结构化解析:语法点+分级句 / 听力考点+句组 / 作文要求+正文。"""
    return make_ok(await _unit_structured_out(db, unit_id))


@router.post("/curriculum/units/{unit_id}/structured/generate", response_model=BaseResponse[dict])
async def generate_unit_structured_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """从单元原文 LLM 解析出结构化(语法点+分级句/听力考点+句组/作文要求+正文),整体覆盖。

    句子均为原文逐字、每句算 0–100 难度。语法点/听力考点 node_id 第二步「关联知识图谱」再填。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.services import curriculum_ai_service
    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id))).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="单元不存在")
    src = await _resolve_unit_source_text(db, unit)
    parsed = await curriculum_ai_service.parse_unit_structured(src)
    counts = await curriculum_service.persist_unit_structured(db, unit_id=unit_id, parsed=parsed)
    await db.commit()
    out = await _unit_structured_out(db, unit_id)
    out["counts"] = counts
    return make_ok(out)


@router.post("/curriculum/units/{unit_id}/structured/link", response_model=BaseResponse[dict])
async def link_unit_structured_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep,
                                   only_unlinked: bool = True):
    """第二步:把单元结构化的 语法点→词法/句法、听力考点→听力 关联到知识图谱。

    命中回填 node;未命中落候选(走「候选审核」,审核通过挂到树上后再点一次即可关联)。
    """
    counts = await curriculum_service.link_unit_sections(
        db, unit_id=unit_id, only_unlinked=only_unlinked)
    await db.commit()
    out = await _unit_structured_out(db, unit_id)
    out["link_counts"] = counts
    return make_ok(out)


@router.get("/curriculum/units/{unit_id}/linked-nodes", response_model=BaseResponse[dict])
async def list_unit_linked_nodes_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """单元考点 = 单元解析里语法点/听力考点已关联到知识图谱的节点(去重)。"""
    items = await curriculum_service.list_unit_linked_nodes(db, unit_id=unit_id)
    return make_ok({"items": items})


# ── 单元重点单词 ↔ 词力通 ────────────────────────────────────────────────
@router.get("/curriculum/units/{unit_id}/words", response_model=BaseResponse[dict])
async def list_unit_words_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """单元已挂的重点单词/词组(连词力通释义/音标)。"""
    from app.services import curriculum_vocab_service
    items = await curriculum_vocab_service.list_unit_words(db, unit_id=unit_id)
    return make_ok({"items": items})


@router.post("/curriculum/units/{unit_id}/words", response_model=BaseResponse[dict])
async def save_unit_words_api(unit_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """把一批单词/词组挂到单元(命中词力通则复用、缺失则新建)。body={items:[{word,phonetic?,meaning?,pos?,type?}], is_core?}。"""
    from app.services import curriculum_vocab_service
    items = body.get("items") or []
    counts = await curriculum_vocab_service.link_unit_words(
        db, unit_id=unit_id, items=items, is_core=bool(body.get("is_core", True)))
    await db.commit()
    out = await curriculum_vocab_service.list_unit_words(db, unit_id=unit_id)
    return make_ok({"items": out, "counts": counts})


@router.delete("/curriculum/units/{unit_id}/words/{word_id}", response_model=BaseResponse[dict])
async def unlink_unit_word_api(unit_id: uuid.UUID, word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """解除某词与单元的挂靠(词力通词条保留)。"""
    from app.services import curriculum_vocab_service
    await curriculum_vocab_service.unlink_unit_word(db, unit_id=unit_id, word_id=word_id)
    await db.commit()
    return make_ok({"ok": True})


@router.post("/curriculum/units/{unit_id}/words/ocr", response_model=BaseResponse[dict])
async def ocr_unit_words_api(unit_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """多图 OCR 解析单词/词组(仅解析返回供人工核对,不落库)。body={images:[dataURL...]}。"""
    from app.services import curriculum_vocab_service
    images = [u for u in (body.get("images") or []) if isinstance(u, str) and u.strip()]
    if not images:
        raise AppError(code=400, message="请至少上传一张图片")
    if len(images) > 20:
        raise AppError(code=400, message="单次最多 20 张图片")
    items = await curriculum_vocab_service.ocr_words_from_images(images)
    return make_ok({"items": items})


@router.post("/curriculum/units/{unit_id}/words/parse-text", response_model=BaseResponse[dict])
async def parse_unit_words_text_api(unit_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """LLM 解析粘贴的单词表文本(仅解析返回供人工核对,不落库)。body={text}。"""
    from app.services import curriculum_vocab_service
    text = (body.get("text") or "").strip()
    if not text:
        raise AppError(code=400, message="请粘贴单词表文本")
    items = await curriculum_vocab_service.parse_words_from_text(text)
    return make_ok({"items": items})


@router.post("/curriculum-unit-sections/{section_id}/link-node", response_model=BaseResponse[dict])
async def manual_link_section_api(section_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """人工挂靠:把某语法点/听力考点关联到图谱里已存在的节点(限 语法→cf/jf、听力→lt)。"""
    node_id = uuid.UUID(str(body.get("node_id")))
    r = await curriculum_service.manual_link_section(db, section_id=section_id, node_id=node_id)
    await db.commit()
    return make_ok(r)


@router.post("/curriculum-unit-sections/{section_id}/new-node", response_model=BaseResponse[dict])
async def new_node_for_section_api(section_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """目录没有→在所选父分类下新建图谱节点(手工标签)并挂靠。body: {parent_id, name}。"""
    parent_id = uuid.UUID(str(body.get("parent_id")))
    r = await curriculum_service.new_node_for_section(
        db, section_id=section_id, parent_id=parent_id,
        name=str(body.get("name") or ""), created_by=admin.id)
    await db.commit()
    return make_ok(r)


@router.post("/unit-passages/{passage_id}/suggest-kp", response_model=BaseResponse[dict])
async def suggest_passage_kp_api(passage_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """AI 给该短文匹配考点(听力→lt/阅读→rc/写作→wr),只返回建议不入库。"""
    import sqlalchemy as _sa
    from app.models.d4_knowledge import CurriculumUnitPassage as _P, CurriculumUnit as _U
    from app.services import kp_suggest_service as kss
    from app.services import kp_prompt_service as kps
    p = (await db.execute(_sa.select(_P).where(_P.id == passage_id))).scalar_one_or_none()
    if p is None:
        raise AppError(code=404, message="短文不存在")
    # 该短文所属单元的「教材+年级+学期」→ 用对应学期定制提示词(无定制回退全局)
    u = (await db.execute(_sa.select(
        _U.textbook_version, _U.grade, _U.semester).where(_U.id == p.unit_id))).first()
    scope = kps.make_scope(u.textbook_version, u.grade, u.semester) if u else None
    refs = await kss.suggest_kps_for_passage(db, p.text, p.kind, scope=scope)
    return make_ok({"items": [{"node_id": str(n), "name": nm, "code": c} for n, nm, c in refs]})


@router.post("/unit-passages/{passage_id}/kp", response_model=BaseResponse[dict])
async def attach_passage_kp_api(passage_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """把考点关联到该短文(人工确认 AI 建议或手动挂)。"""
    import sqlalchemy as _sa
    from app.models.d4_knowledge import UnitPassageKp as _PK
    node_id = uuid.UUID(str(body.get("node_id")))
    exists = (await db.execute(_sa.select(_PK).where(
        _PK.passage_id == passage_id, _PK.node_id == node_id))).scalar_one_or_none()
    if exists is None:
        db.add(_PK(passage_id=passage_id, node_id=node_id))
        await db.commit()
    return make_ok({"ok": True})


@router.delete("/unit-passages/{passage_id}/kp/{node_id}", response_model=BaseResponse[dict])
async def detach_passage_kp_api(passage_id: uuid.UUID, node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """取消该短文的某考点关联。"""
    import sqlalchemy as _sa
    from app.models.d4_knowledge import UnitPassageKp as _PK
    await db.execute(_sa.delete(_PK).where(_PK.passage_id == passage_id, _PK.node_id == node_id))
    await db.commit()
    return make_ok({"ok": True})


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

def _to_pq_item(q, passage: str | None = None, kp_names: list | None = None) -> PlatformQuestionItem:
    return PlatformQuestionItem(
        id=q.id, type=q.type, parent_real_id=q.parent_real_id, is_fallback=q.is_fallback,
        question_type=q.question_type, stem=q.stem, options=q.options, answer=q.answer,
        explanation=q.explanation, difficulty=q.difficulty, status=q.status,
        sim_version=q.sim_version, kp_names=kp_names or [],
        block_id=q.block_id, passage=passage,
    )


@router.get("/sim-papers", response_model=BaseResponse[dict])
async def list_sim_papers_api(
    db: DbDep, admin: AdminDep, status: str | None = None,
    skip: int = 0, limit: int = 20,
):
    """仿真题按来源真题卷聚合(供「仿真题审核」先按卷列,再点开看整卷)。分页。"""
    from app.services import platform_question_service as pqs
    items, total = await pqs.list_sim_papers(db, status=status, skip=skip, limit=limit)
    return make_ok({"total": total, "items": items})


@router.get("/platform-questions", response_model=BaseResponse[PlatformQuestionListOut])
async def list_platform_questions_api(
    db: DbDep, admin: AdminDep,
    type: str | None = None, status: str | None = None,
    node_id: uuid.UUID | None = None, source_paper_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20,
):
    """平台题分页查询(真题/仿真,可按 type/status/node/来源卷 过滤)。"""
    from app.services import platform_question_service as pqs
    rows, total = await pqs.list_platform_questions(
        db, type=type, status=status, node_id=node_id,
        source_paper_id=source_paper_id, skip=skip, limit=limit)
    pmap = await pqs.passages_for(db, [r.block_id for r in rows if r.block_id])
    # 各题关联考点名(继承母题)
    import sqlalchemy as _sa
    from app.models.d16_question_domain import PlatformQuestionKp as _PQK
    from app.models.d15_knowledge_graph import KnowledgeNode as _KN
    kpmap: dict = {}
    if rows:
        for qid, nm in (await db.execute(
            _sa.select(_PQK.question_id, _KN.name)
            .join(_KN, _KN.id == _PQK.node_id)
            .where(_PQK.question_id.in_([r.id for r in rows])))).all():
            kpmap.setdefault(qid, []).append(nm)
    return make_ok(PlatformQuestionListOut(
        total=total, items=[_to_pq_item(r, pmap.get(r.block_id), kpmap.get(r.id)) for r in rows]))


@router.post("/platform-questions", response_model=BaseResponse[RealImportItemOut])
async def import_real_question_api(body: RealQuestionIn, db: DbDep, admin: AdminDep):
    """导入一道真题 → platform_question(type=real),kp_names 受控匹配挂 node(TK1)。"""
    from app.services import platform_question_service as pqs
    res = await pqs.import_real_question(
        db, stem=body.stem, answer=body.answer, options=body.options,
        question_type=body.question_type, explanation=body.explanation,
        difficulty=body.difficulty, meta=body.meta, kp_names=body.kp_names,
        stage_hint=body.stage_hint, question_no=body.question_no, status=body.status)
    await db.commit()
    return make_ok(RealImportItemOut(
        question_id=res.question_id, matched_nodes=res.matched_nodes, candidates=res.candidates))


@router.post("/platform-questions/bulk", response_model=BaseResponse[RealImportBulkOut])
async def import_real_questions_bulk_api(body: RealQuestionBulkIn, db: DbDep, admin: AdminDep):
    """批量导入真题(校对后一次落多题);单题失败 savepoint 隔离,不连累其余(TK1)。

    整卷:先建一份 platform_paper(批次 meta + 试卷名),每题挂 paper_id + section。
    题组:同一 block_key 的小问先建一份 passage(短文存一份),再以 block_id 关联。
    """
    from app.services import platform_question_service as pqs
    # 整卷建一份试卷(默认 draft,导入完成后整卷发布)
    paper_id = await pqs.create_paper(db, name=body.paper_name, meta=body.meta)
    # 先按 block_key 建 passage(取该组任一非空 passage 文本)
    block_pid: dict[str, uuid.UUID] = {}
    for it in body.items:
        if it.block_key and it.block_key not in block_pid and (it.passage or "").strip():
            try:
                async with db.begin_nested():
                    block_pid[it.block_key] = await pqs.create_passage(db, text=it.passage.strip())
            except Exception:  # noqa: BLE001
                pass
    items: list[RealImportItemOut] = []
    failed = 0
    for it in body.items:
        try:
            async with db.begin_nested():
                res = await pqs.import_real_question(
                    db, stem=it.stem, answer=it.answer, options=it.options,
                    question_type=it.question_type, explanation=it.explanation,
                    difficulty=it.difficulty, meta=(it.meta or body.meta), kp_names=it.kp_names,
                    stage_hint=it.stage_hint or body.stage_hint,
                    question_no=it.question_no, status=body.status or it.status,
                    block_id=block_pid.get(it.block_key) if it.block_key else None,
                    paper_id=paper_id, section=it.section)
            items.append(RealImportItemOut(
                question_id=res.question_id, matched_nodes=res.matched_nodes, candidates=res.candidates))
        except Exception:  # noqa: BLE001
            failed += 1
    await db.commit()
    return make_ok(RealImportBulkOut(
        imported=len(items), failed=failed, paper_id=paper_id, items=items))


@router.post("/platform-questions/{real_id}/gen-sim", response_model=BaseResponse[GenSimOut])
async def gen_sim_from_real_api(real_id: uuid.UUID, db: DbDep, admin: AdminDep, count: int = 3):
    """由真题预生成 N 道仿真(继承母题 KP,parent_real_id 必填)。"""
    from app.services import platform_question_service as pqs
    sim_ids = await pqs.generate_sim_from_real(db, real_id=real_id, count=count)
    await db.commit()
    return make_ok(GenSimOut(generated=len(sim_ids), sim_ids=sim_ids))


@router.post("/platform-questions/gen-sim-bulk", response_model=BaseResponse[dict])
async def gen_sim_bulk_api(body: GenSimBulkIn, db: DbDep, admin: AdminDep):
    """派生仿真(后台异步):秒回 job_id,前端轮询 gen-sim-jobs/{job_id} 看进度。

    短文题组整组改写、单题逐题,版本按题位累加。大量 LLM 改写在后台跑,不阻塞请求。
    """
    from app.services import sim_gen_job_service as sgj
    job_id = sgj.start(body.question_ids, body.count)
    return make_ok({"job_id": job_id, "per_question": body.count})


@router.get("/platform-questions/gen-sim-jobs/{job_id}", response_model=BaseResponse[dict])
async def gen_sim_job_status_api(job_id: str, db: DbDep, admin: AdminDep):
    """派生仿真后台任务进度。"""
    from app.services import sim_gen_job_service as sgj
    st = sgj.get_status(job_id)
    if st is None:
        raise AppError(code=404, message="任务不存在(可能已重启)")
    return make_ok({"job_id": job_id, **st})


@router.post("/kp-nodes/{node_id}/gen-sim", response_model=BaseResponse[GenSimOut])
async def gen_sim_for_node_api(
    node_id: uuid.UUID, db: DbDep, admin: AdminDep,
    dimension: str = "verb_fill", count: int = 3, force: bool = False,
):
    """按考点「反向生成」仿真(P0):dimension=verb_fill 动词填空 / vocab_form 词汇运用 /
    dictation 拼写 / grammar 语法混合。生成 is_fallback 仿真并挂该节点,落 draft 待审。
    node 已有真题母题时默认跳过(应走真题派生),force=true 可强制。"""
    from app.services import platform_question_service as pqs
    sim_ids = await pqs.generate_fallback_sim(
        db, node_id=node_id, count=count, dimension=dimension, force=force, status="draft")
    await db.commit()
    return make_ok(GenSimOut(generated=len(sim_ids), sim_ids=sim_ids))


# ─── 平台试卷(整卷聚合 / 发布 / 选题仿真)────────────────────────────────────────

def _to_paper_item(p, cnt: int = 0, pub: int = 0) -> PaperListItem:
    return PaperListItem(
        id=p.id, name=p.name, textbook_version=p.textbook_version, stage=p.stage,
        grade=p.grade, semester=p.semester, region_name=p.region_name,
        exam_type=p.exam_type, status=p.status, question_count=cnt,
        published_count=pub, created_at=p.created_at,
        source_file_url=getattr(p, "source_file_url", None),
        source_filename=getattr(p, "source_filename", None),
        parse_status=getattr(p, "parse_status", None),
        parse_error=(p.meta or {}).get("parse_error") if getattr(p, "meta", None) else None,
        convert_status=(p.meta or {}).get("convert_status") if getattr(p, "meta", None) else None,
        year=getattr(p, "year", None),
    )


@router.get("/platform-papers", response_model=BaseResponse[PaperListOut])
async def list_platform_papers_api(
    db: DbDep, admin: AdminDep, status: str | None = None,
    textbook_version: str | None = None, stage: str | None = None,
    grade: str | None = None, exam_type: str | None = None,
    region_code: str | None = None, year: int | None = None,
    skip: int = 0, limit: int = 20,
):
    """平台试卷分页(一卷一条,含题数/已发布数);可按教材/学段/年级/地区/考试/年份筛选。"""
    from app.services import platform_question_service as pqs
    rows, total = await pqs.list_papers(
        db, status=status, textbook_version=textbook_version, stage=stage,
        grade=grade, exam_type=exam_type, region_code=region_code, year=year,
        skip=skip, limit=limit)
    return make_ok(PaperListOut(
        total=total, items=[_to_paper_item(p, c, pub) for p, c, pub in rows]))


@router.get("/platform-papers/{paper_id}", response_model=BaseResponse[PaperDetailOut])
async def get_platform_paper_api(paper_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """试卷详情:整卷全部真题(按题号,带大题名/题组短文)。"""
    from app.services import platform_question_service as pqs
    paper, qs, pmap = await pqs.paper_questions(db, paper_id)
    if paper is None:
        raise AppError(code=404, message="试卷不存在")
    pub = sum(1 for q in qs if q.status == "published")
    kpmap = await pqs.kps_of_questions(db, [q.id for q in qs])
    items = [PaperQuestionItem(
        id=q.id, question_no=q.question_no, section=q.section,
        question_type=q.question_type, stem=q.stem, answer=q.answer,
        difficulty=q.difficulty, status=q.status, block_id=q.block_id,
        passage=pmap.get(q.block_id) if q.block_id else None,
        kps=[QuestionKpRef(node_id=nid, name=name, code=code)
             for nid, name, code in kpmap.get(q.id, [])],
    ) for q in qs]
    return make_ok(PaperDetailOut(paper=_to_paper_item(paper, len(qs), pub), questions=items))


@router.post("/platform-questions/{question_id}/kp", response_model=BaseResponse[list[QuestionKpRef]])
async def attach_question_kp_api(question_id: uuid.UUID, body: AttachKpIn, db: DbDep, admin: AdminDep):
    """给某真题挂一个受控知识点(节点须存在);返回该题最新 KP 列表。"""
    from app.services import platform_question_service as pqs
    from app.models.d15_knowledge_graph import KnowledgeNode
    node = await db.get(KnowledgeNode, body.node_id)
    if node is None:
        raise AppError(code=404, message="知识点不存在")
    await pqs.attach_node(db, question_id, body.node_id)
    await db.commit()
    kps = (await pqs.kps_of_questions(db, [question_id])).get(question_id, [])
    return make_ok([QuestionKpRef(node_id=n, name=nm, code=c) for n, nm, c in kps])


@router.post("/platform-questions/kp-bulk", response_model=BaseResponse[dict])
async def attach_kp_bulk_api(body: KpBulkAttachIn, db: DbDep, admin: AdminDep):
    """批量挂载题↔知识点(采纳全部 AI 建议)。幂等。返回挂载条数。"""
    from app.services import platform_question_service as pqs
    n = 0
    for p in body.pairs:
        if await pqs.attach_node(db, p.question_id, p.node_id):
            n += 1
    await db.commit()
    return make_ok({"attached": n})


@router.delete("/platform-questions/{question_id}/kp/{node_id}", response_model=BaseResponse[list[QuestionKpRef]])
async def detach_question_kp_api(question_id: uuid.UUID, node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """解挂某真题的一个知识点;返回该题最新 KP 列表。"""
    from app.services import platform_question_service as pqs
    await pqs.detach_node(db, question_id, node_id)
    await db.commit()
    kps = (await pqs.kps_of_questions(db, [question_id])).get(question_id, [])
    return make_ok([QuestionKpRef(node_id=n, name=nm, code=c) for n, nm, c in kps])


@router.post("/platform-papers/{paper_id}/suggest-kp", response_model=BaseResponse[SuggestKpOut])
async def suggest_paper_kp_api(paper_id: uuid.UUID, db: DbDep, admin: AdminDep,
                               body: SuggestKpIn | None = None):
    """AI 建议:按题型默认提示词给每题挑考点;可按 sections 限大题、prompt_id 指定提示词。"""
    from app.schemas.kp import KpProposal
    from app.services import kp_suggest_service as kss
    matches, proposals = await kss.suggest_kps_for_paper(
        db, paper_id,
        sections=(body.sections if body else None),
        prompt_id=(body.prompt_id if body else None),
        skip_attached=(body.skip_attached if body else False))
    items = []
    for qid in set(matches) | set(proposals):
        refs = matches.get(qid) or []
        props = proposals.get(qid) or []
        if not refs and not props:
            continue
        items.append(SuggestKpItem(
            question_id=qid,
            suggestions=[QuestionKpRef(node_id=n, name=nm, code=c) for n, nm, c in refs],
            proposals=[KpProposal(name=nm, parent_node_id=pid, parent_name=pn) for nm, pid, pn in props],
        ))
    return make_ok(SuggestKpOut(items=items))


@router.get("/kp-prompts", response_model=BaseResponse[KpPromptsOut])
async def get_kp_prompts_api(db: DbDep, admin: AdminDep, scope: str | None = None):
    """知识点 AI 提示词(按题型)。scope=「教材版本|年级|学期」则取该学期定制(无则回退全局)。"""
    from app.services import kp_prompt_service as kps
    prompts = await kps.get_prompts(db, scope)
    return make_ok(KpPromptsOut(
        prompts=[KpPromptItem(**p) for p in prompts],
        passage_include_skill=await kps.get_passage_include_skill(db, scope)))


@router.put("/kp-prompts", response_model=BaseResponse[KpPromptsOut])
async def save_kp_prompts_api(body: KpPromptsIn, db: DbDep, admin: AdminDep):
    """保存知识点 AI 提示词(整体覆盖,每题型至多一个默认)。body.scope 非空则存该学期定制。"""
    from app.services import kp_prompt_service as kps
    saved = await kps.save_prompts(
        db, prompts=[p.model_dump() for p in body.prompts], updated_by=admin.id, scope=body.scope,
        passage_include_skill=body.passage_include_skill)
    await db.commit()
    return make_ok(KpPromptsOut(
        prompts=[KpPromptItem(**p) for p in saved],
        passage_include_skill=await kps.get_passage_include_skill(db, body.scope)))


@router.get("/kp-prompts/scopes", response_model=BaseResponse[list[str]])
async def list_kp_prompt_scopes_api(db: DbDep, admin: AdminDep):
    """已定制(有独立提示词)的学期 scope 串列表,如 ["译林版|七年级|上", ...]。"""
    from app.services import kp_prompt_service as kps
    return make_ok(await kps.list_scopes(db))


@router.delete("/kp-prompts/scope", response_model=BaseResponse[dict])
async def delete_kp_prompt_scope_api(db: DbDep, admin: AdminDep, scope: str):
    """删除某学期的提示词定制,恢复为继承全局默认。"""
    from app.services import kp_prompt_service as kps
    ok = await kps.delete_scope(db, scope)
    await db.commit()
    return make_ok({"deleted": ok})


@router.post("/kp-suggest-text", response_model=BaseResponse[list[QuestionKpRef]])
async def suggest_kp_text_api(body: SuggestTextIn, db: DbDep, admin: AdminDep):
    """一段正文(教材等)→ 受控考点 AI 建议(用该来源类型的提示词+关注分类)。"""
    from app.services import kp_suggest_service as kss
    refs = await kss.suggest_kps_for_text(db, body.text, source_type=body.source_type, stage=body.stage)
    return make_ok([QuestionKpRef(node_id=n, name=nm, code=c) for n, nm, c in refs])


@router.post("/platform-papers/delete", response_model=BaseResponse[dict])
async def delete_platform_papers_api(body: PaperDeleteIn, db: DbDep, admin: AdminDep):
    """批量删除试卷(连带其真题/仿真/短文/KP 边/错题作答引用)。"""
    from app.services import platform_question_service as pqs
    n = await pqs.delete_papers(db, body.paper_ids)
    await db.commit()
    return make_ok({"deleted": n})


@router.post("/platform-papers/{paper_id}/section-kp", response_model=BaseResponse[dict])
async def attach_section_kp_api(paper_id: uuid.UUID, body: SectionKpIn, db: DbDep, admin: AdminDep):
    """按大题一键挂:把某大题下所有真题挂同一个受控知识点。返回挂载题数。"""
    from app.services import platform_question_service as pqs
    from app.models.d15_knowledge_graph import KnowledgeNode
    if await db.get(KnowledgeNode, body.node_id) is None:
        raise AppError(code=404, message="知识点不存在")
    n = await pqs.attach_node_to_section(db, paper_id=paper_id, section=body.section, node_id=body.node_id)
    await db.commit()
    return make_ok({"attached": n})


@router.post("/platform-papers/{paper_id}/publish", response_model=BaseResponse[PaperListItem])
async def publish_platform_paper_api(paper_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """整卷发布:试卷下所有真题置 published + 试卷置 published。"""
    from app.services import platform_question_service as pqs
    await pqs.publish_paper(db, paper_id)
    paper, qs, _ = await pqs.paper_questions(db, paper_id)
    await db.commit()
    pub = sum(1 for q in qs if q.status == "published")
    return make_ok(_to_paper_item(paper, len(qs), pub))


@router.post("/platform-questions/{question_id}/review", response_model=BaseResponse[PlatformQuestionItem])
async def review_platform_question_api(
    question_id: uuid.UUID, body: ReviewRequest, db: DbDep, admin: AdminDep,
):
    """审核平台题:approve→published,reject→retired。"""
    from app.services import platform_question_service as pqs
    q = await pqs.review_platform_question(db, question_id=question_id, approve=body.approve)
    await db.commit()
    return make_ok(_to_pq_item(q))


@router.post("/platform-questions/review-bulk", response_model=BaseResponse[dict])
async def review_platform_questions_bulk_api(body: ReviewBulkIn, db: DbDep, admin: AdminDep):
    """批量审核仿真题(整卷/选中):approve→published,reject→retired。"""
    from app.services import platform_question_service as pqs
    n = await pqs.review_platform_questions_bulk(
        db, question_ids=body.question_ids, approve=body.approve)
    await db.commit()
    return make_ok({"updated": n, "status": "published" if body.approve else "retired"})


# ─── 真题抽题(TK2:上传 PDF/图片 → 异步 OCR/拆题 → 待校对)──────────────────────────

@router.post("/platform-questions/extract", response_model=BaseResponse[RealExtractCreatedOut])
async def extract_real_questions_api(
    db: DbDep, admin: AdminDep,
    file: UploadFile | None = File(None, description="真题 PDF(文本版)或 Word(.docx)"),
    image_urls: str | None = Form(None, description="图片 URL 列表(JSON 数组字符串,走 OCR)"),
):
    """传 PDF / Word(取文本)或图片 URL(run_ocr)→ 秒回 job_id,后台拆题。"""
    import json as _json
    from app.services import real_extract_service as res, pdf_upload_service as pus
    if file is not None:
        name = (file.filename or "").lower()
        if name.endswith(".docx"):
            file_id = pus.save_upload_docx(await file.read())
            job = await res.create_job(db, source="docx", file_id=file_id)
        elif name.endswith(".pdf") or not name:
            file_id = pus.save_upload(await file.read())
            job = await res.create_job(db, source="pdf", file_id=file_id)
        else:
            raise AppError(code=400, message="仅支持 PDF 或 Word(.docx)文件")
    elif image_urls:
        try:
            urls = _json.loads(image_urls)
            assert isinstance(urls, list) and urls
        except Exception:
            raise AppError(code=400, message="image_urls 需为非空 JSON 数组")
        job = await res.create_job(db, source="image", image_urls=urls)
    else:
        raise AppError(code=400, message="请上传 PDF 文件或提供 image_urls")
    await db.commit()
    res.schedule(job.id)
    return make_ok(RealExtractCreatedOut(job_id=job.id))


_PAPER_CT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}


@router.post("/platform-questions/batch-upload", response_model=BaseResponse[dict])
async def batch_upload_papers_api(
    db: DbDep, admin: AdminDep,
    files: list[UploadFile] = File(..., description="多份真题原卷(word/pdf)"),
    meta: str | None = Form(None, description="共享元信息 JSON(教材/学段/年级/学期/地区/考试)"),
):
    """批量上传真题:每份文件传 COS + 建**草稿占位试卷**(0 题,挂原卷直链),题目延后解析。"""
    import json as _json
    import uuid as _uuid
    from app.services import pdf_upload_service as pus, platform_question_service as pqs
    if not files:
        raise AppError(code=400, message="请至少选择一个文件")
    if len(files) > 500:
        raise AppError(code=400, message="单次最多 500 份")
    m = {}
    if meta:
        try:
            m = _json.loads(meta) or {}
        except Exception:
            raise AppError(code=400, message="meta 需为 JSON")
    results: list[dict] = []
    doc_paper_ids: list = []
    # 唯一性判断:试卷名(=文件名去扩展名)与库里已有重复的跳过;同批次内重名也只留一份
    stems = [(f.filename or "").rsplit(".", 1)[0] if "." in (f.filename or "") else (f.filename or "") for f in files]
    dup_names = await pqs.existing_paper_names(db, stems)
    seen_stems: set = set()
    for f in files:
        fname = f.filename or "未命名"
        ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
        if ext not in _PAPER_CT:
            results.append({"filename": fname, "ok": False, "error": "仅支持 pdf / doc / docx"})
            continue
        stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        if stem in dup_names or stem in seen_stems:
            results.append({"filename": fname, "ok": False, "duplicate": True, "error": "试卷名已存在,已跳过"})
            continue
        seen_stems.add(stem)
        try:
            data = await f.read()
            if len(data) > 300 * 1024 * 1024:
                results.append({"filename": fname, "ok": False, "error": "文件过大(上限 300MB)"})
                continue
            key = f"papers/{_uuid.uuid4().hex}{ext}"
            url = await pus.upload_bytes_to_cos(data, key, _PAPER_CT[ext])
            # 也存一份本地(供之后「解析原题目」用):按后缀存对应格式
            if ext == ".docx":
                file_id, src = pus.save_upload_docx(data), "docx"
            elif ext == ".doc":
                file_id, src = pus.save_upload_doc(data), "doc"
            else:
                file_id, src = pus.save_upload(data), "pdf"
            stem = fname.rsplit(".", 1)[0] if "." in fname else fname
            pmeta = {**m, "file_id": file_id, "source": src}
            # 按**该文件名**单独解析地区(整批可能是不同城市),命中则覆盖共享地区
            from app.services import region_service
            rc, rn = await region_service.region_from_name(db, stem)
            if rc:
                pmeta.update(region_code=rc, region_name=rn)
                pmeta.pop("city_code", None)
                pmeta.pop("province_code", None)
            if src == "doc":
                pmeta["convert_status"] = "pending"      # .doc 待后台转 PDF
            pid = await pqs.create_paper_placeholder(
                db, name=stem, meta=pmeta,
                source_file_url=url, source_filename=fname)
            if src == "doc":
                doc_paper_ids.append(pid)
            results.append({"filename": fname, "ok": True, "paper_id": str(pid),
                            "file_url": url, "cos": bool(url)})
        except Exception as exc:  # noqa: BLE001
            results.append({"filename": fname, "ok": False, "error": str(exc)})
    await db.commit()
    if doc_paper_ids:                                    # 后台并发把 .doc 转 PDF(不阻塞上传)
        pqs.schedule_doc_conversions(doc_paper_ids)
    ok = sum(1 for r in results if r["ok"])
    return make_ok({"results": results, "ok": ok, "total": len(files)})


@router.post("/platform-papers/{paper_id}/convert-doc", response_model=BaseResponse[dict])
async def convert_paper_doc_api(paper_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """重试:把该 .doc 试卷用 LibreOffice 转成 PDF(转换成功后即可「解析原题目」)。"""
    from app.services import platform_question_service as pqs
    r = await pqs.convert_paper_doc(db, paper_id=paper_id)
    return make_ok(r)


@router.post("/platform-papers/{paper_id}/parse", response_model=BaseResponse[dict])
async def parse_paper_api(paper_id: uuid.UUID, db: DbDep, admin: AdminDep, mode: str | None = None):
    """解析某份(批量上传的)试卷的原始文件 → 拆题自动入库为草稿。标注 parse_status。

    mode=llm:排版复杂/结构化漏题时,强制走 LLM 整卷解析(不吃正则规则)。
    """
    from app.services import platform_question_service as pqs
    r = await pqs.parse_paper_questions(db, paper_id=paper_id, force_llm=(mode == "llm"))
    await db.commit()
    return make_ok(r)


@router.post("/uploads/presign", response_model=BaseResponse[PresignOut])
async def admin_upload_presign(body: PresignRequest, admin: AdminDep):
    """平台后台图片上传预签名(真题图片直传 COS→拿 file_url 走 OCR)。dev 返回 mock。"""
    from app.services.upload_service import ALLOWED_CONTENT_TYPES, generate_presign
    if body.content_type not in ALLOWED_CONTENT_TYPES:
        allowed = "、".join(ALLOWED_CONTENT_TYPES)
        raise AppError(code=400, message=f"不支持的图片类型:{body.content_type},允许:{allowed}")
    result = generate_presign(user_id=admin.id, content_type=body.content_type)
    return make_ok(PresignOut(**result))


@router.get("/platform-questions/extract-jobs/{job_id}", response_model=BaseResponse[RealExtractJobOut])
async def get_real_extract_job_api(job_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """查真题抽题任务进度 + 取待校对题(前端轮询,校对后调 /platform-questions/bulk 导入)。"""
    from app.services import real_extract_service as res
    job = await res.get_job(db, job_id)
    if job is None:
        raise AppError(code=404, message="抽题任务不存在")
    return make_ok(RealExtractJobOut(
        job_id=job.id, source=job.source, status=job.status, error=job.error,
        parsed=[ParsedRealQuestion(**p) for p in (job.parsed or [])]))


# ─── 地区维护（行政区划 region 表,唯一数据源)────────────────────────────────────

@router.get("/regions", response_model=BaseResponse[list[RegionItem]])
async def list_regions_admin(db: DbDep, admin: AdminDep, parent: str | None = None):
    """后台懒加载地区:无 parent → 省;有 parent → 下级。"""
    from app.services import region_service
    return make_ok([RegionItem(**r) for r in await region_service.list_children(db, parent)])


@router.post("/regions", response_model=BaseResponse[RegionItem])
async def create_region_admin(body: RegionIn, db: DbDep, admin: AdminDep):
    """新增一个地区(省/市/区县/乡镇)。code 须唯一、上级须存在。"""
    from app.services import region_service
    r = await region_service.create_region(
        db, code=body.code.strip(), name=body.name.strip(),
        parent_code=body.parent_code, level=body.level)
    await db.commit()
    return make_ok(RegionItem(code=r.code, name=r.name, parent_code=r.parent_code, level=r.level, leaf=True))


@router.put("/regions/{code}", response_model=BaseResponse[RegionItem])
async def update_region_admin(code: str, body: RegionRename, db: DbDep, admin: AdminDep):
    """改地区名称。"""
    from app.services import region_service
    r = await region_service.update_region(db, code=code, name=body.name.strip())
    await db.commit()
    return make_ok(RegionItem(code=r.code, name=r.name, parent_code=r.parent_code, level=r.level, leaf=True))


@router.delete("/regions/{code}", response_model=BaseResponse[dict])
async def delete_region_admin(code: str, db: DbDep, admin: AdminDep):
    """删地区(有下级则拒绝,先删下级)。"""
    from app.services import region_service
    await region_service.delete_region(db, code=code)
    await db.commit()
    return make_ok({"deleted": code})


# ─── 知识节点资源管理（R6 资源层补全）────────────────────────────────────────────

def _to_node_resource_item(r, node_name: str | None = None) -> NodeResourceItem:
    return NodeResourceItem(
        id=r.id, node_id=r.node_id, node_name=node_name, resource_type=r.resource_type,
        dimension=r.dimension, title=r.title, content_md=r.content_md, media_url=r.media_url,
        resource_json=r.resource_json, status=r.status,
    )


@router.get("/node-resources", response_model=BaseResponse[NodeResourceListOut])
async def list_node_resources_api(
    db: DbDep, admin: AdminDep, status: str | None = "draft",
    node_id: uuid.UUID | None = None, resource_type: str | None = None,
    unit_id: uuid.UUID | None = None, skip: int = 0, limit: int = 20,
):
    from app.services import node_resource_service as nrs
    from app.models.d15_knowledge_graph import KnowledgeNode
    status = status or None        # 空串 = 全部状态
    rows, total = await nrs.list_for_review(db, status=status, node_id=node_id,
                                            resource_type=resource_type, unit_id=unit_id,
                                            skip=skip, limit=limit)
    nids = {r.node_id for r in rows}
    names = dict((await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name).where(KnowledgeNode.id.in_(nids)))).all()) if nids else {}
    return make_ok(NodeResourceListOut(
        total=total, items=[_to_node_resource_item(r, names.get(r.node_id)) for r in rows]))


@router.get("/curriculum/units/{unit_id}/content-overview",
            response_model=BaseResponse[UnitContentOverviewOut])
async def unit_content_overview_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """单元补全总览:每个对齐节点 × 六维讲解状态(缺失/草稿/已发布),供发布前预览+补全。"""
    from app.services import node_resource_service as nrs
    nodes = await nrs.unit_content_overview(db, unit_id=unit_id)
    return make_ok(UnitContentOverviewOut(total_nodes=len(nodes), items=nodes))


@router.post("/curriculum/units/{unit_id}/publish", response_model=BaseResponse[UnitPublishOut])
async def publish_unit_api(unit_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """一键发布整单元:该单元所有对齐节点下 draft/reviewing 讲解 → published。"""
    from app.services import node_resource_service as nrs
    r = await nrs.publish_unit(db, unit_id=unit_id, reviewer_id=admin.id)
    await db.commit()
    return make_ok(UnitPublishOut(**r))


# ─── 内容版本对比 / 审核(C2)────────────────────────────────────────
@router.get("/node-resource-versions/{version_id}/diff", response_model=BaseResponse[VersionDiffOut])
async def version_diff_api(version_id: uuid.UUID, db: DbDep, admin: AdminDep, against: str = "current"):
    """取待审版本与对比基准(当前线上 / 另一版本)的两份正文,供前端行级 diff。"""
    from app.services import node_resource_service as nrs
    return make_ok(VersionDiffOut(**(await nrs.version_diff(db, version_id=version_id, against=against))))


@router.post("/node-resource-versions/{version_id}/approve", response_model=BaseResponse[dict])
async def approve_version_api(version_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """审核通过待审版本 → 替换线上、旧版归档。"""
    from app.services import node_resource_service as nrs
    r = await nrs.approve_version(db, version_id=version_id, reviewer_id=admin.id)
    await db.commit()
    return make_ok({k: str(v) for k, v in r.items()})


@router.post("/node-resource-versions/{version_id}/reject", response_model=BaseResponse[dict])
async def reject_version_api(version_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """驳回待审版本(线上不变)。"""
    from app.services import node_resource_service as nrs
    r = await nrs.reject_version(db, version_id=version_id, reviewer_id=admin.id)
    await db.commit()
    return make_ok({k: str(v) for k, v in r.items()})


@router.get("/node-resources/{resource_id}/versions", response_model=BaseResponse[VersionListOut])
async def list_versions_api(resource_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """某讲解的版本历史(版本号倒序),供查看/对比/回滚。"""
    from app.services import node_resource_service as nrs
    rows = await nrs.list_versions(db, resource_id=resource_id)
    items = [VersionItem(id=r.id, version_no=r.version_no, source=r.source, status=r.status,
                         content_md=r.content_md, created_at=r.created_at, reviewed_at=r.reviewed_at)
             for r in rows]
    return make_ok(VersionListOut(resource_id=resource_id, total=len(items), items=items))


@router.post("/node-resources/{resource_id}/rollback/{version_id}", response_model=BaseResponse[dict])
async def rollback_version_api(resource_id: uuid.UUID, version_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """回滚:把某历史(archived)版本重新提升为线上。"""
    from app.services import node_resource_service as nrs
    r = await nrs.rollback_to_version(db, resource_id=resource_id, version_id=version_id, reviewer_id=admin.id)
    await db.commit()
    return make_ok({k: str(v) for k, v in r.items()})


@router.post("/node-resources", response_model=BaseResponse[NodeResourceItem])
async def add_node_resource_api(body: AddResourceIn, db: DbDep, admin: AdminDep):
    from app.services import node_resource_service as nrs
    if body.resource_type == "lecture":
        if not body.dimension or not body.content_md:
            raise AppError(code=400, message="lecture 需 dimension + content_md")
        # C1:走版本流——覆盖已发布讲解则产生待审新版(不覆盖线上)
        ret = await nrs.submit_lecture_version(
            db, node_id=body.node_id, dimension=body.dimension, content_md=body.content_md,
            media_url=body.media_url, source="manual", status_if_new=body.status, created_by=admin.id)
        await db.commit()
        from app.models.d19_node_resource import NodeResource as _NR
        r = (await db.execute(select(_NR).where(_NR.id == ret["resource_id"]))).scalar_one()
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


# ─── 长难句管理（抽取 / 审核 / 配置,复用 R6 审核范式）───────────────────────────

def _to_ls_admin_item(ls) -> LSAdminItem:
    return LSAdminItem(
        id=ls.id, text=ls.text, source_kind=ls.source_kind, status=ls.status,
        syntax_points=(ls.analysis_json or {}).get("syntax_points", []),
        difficulty=ls.difficulty, textbook_version=ls.textbook_version, stage=ls.stage,
        grade=ls.grade, semester=ls.semester, exam_type=ls.exam_type)


@router.get("/long-sentences/textbook-units", response_model=BaseResponse[list])
async def ls_textbook_units_api(db: DbDep, admin: AdminDep):
    """教材抽取可选单元(有阅读短文的),供级联多选 版本/年级/册/单元。"""
    from app.services import long_sentence_service as lss
    return make_ok(await lss.textbook_extract_units(db))


@router.get("/long-sentences/real-dimensions", response_model=BaseResponse[dict])
async def ls_real_dimensions_api(db: DbDep, admin: AdminDep):
    """平台真题可选维度去重值,供多选 版本/学段/年级/册/考试类型/地区。"""
    from app.services import long_sentence_service as lss
    return make_ok(await lss.real_extract_dimensions(db))


@router.post("/long-sentences/extract", response_model=BaseResponse[LSExtractOut])
async def extract_long_sentences_api(body: LSExtractIn, db: DbDep, admin: AdminDep):
    """手动触发平台长难句抽取(幂等)。source: config|all|platform_real|textbook;
    filters 按维度精确挑范围(教材:textbook_version/grade/semester/unit_ids;
    真题:textbook_version/stage/grade/semester/exam_type/region,均为多值列表)。"""
    from app.services import long_sentence_service as lss
    source = body.source or "config"
    if source == "config":
        sources = None
    elif source == "all":
        sources = list(lss._SOURCE_KIND_TO_FN)
    elif source in lss._SOURCE_KIND_TO_FN:
        sources = [source]
    else:
        raise AppError(code=400, message="不支持的抽取来源")
    st = await lss.run_extract(db, sources=sources, limit=body.limit, filters=body.filters or None)
    return make_ok(LSExtractOut(created=st.created, long_kept=st.long_kept, edges=st.edges,
                                candidates=st.candidates, skipped_done=st.skipped_done))


@router.post("/long-sentences/reanalyze", response_model=BaseResponse[dict])
async def reanalyze_long_sentences_api(
    db: DbDep, admin: AdminDep, status: str | None = None, limit: int = 200, publish: bool = False,
):
    """重新解析已有长难句(后台异步,刷新为新结构;可选顺带发布)。秒回 job_id,轮询进度。

    status:只重解析某状态(空=全部);publish=true 同时把这些发布(便于造测试数据)。
    """
    from app.services import ls_reanalyze_job_service as lrj
    job_id = lrj.start(only_status=status, limit=limit, publish=publish)
    return make_ok({"job_id": job_id})


@router.get("/long-sentences/reanalyze-jobs/{job_id}", response_model=BaseResponse[dict])
async def reanalyze_ls_job_status_api(job_id: str, db: DbDep, admin: AdminDep):
    """重新解析后台任务进度。"""
    from app.services import ls_reanalyze_job_service as lrj
    st = lrj.get_status(job_id)
    if st is None:
        raise AppError(code=404, message="任务不存在(可能已重启)")
    return make_ok({"job_id": job_id, **st})


@router.post("/long-sentences/paraphrase-backfill", response_model=BaseResponse[dict])
async def backfill_paraphrase_api(db: DbDep, admin: AdminDep, limit: int = 50,
                                  only_missing: bool = True, max_tokens_budget: int = 200000):
    """给存量长难句补「释义检测」探针(Phase2):LLM 生成释义单选+诊断干扰项,写回 analysis_json.paraphrase。
    only_missing=true 只补缺失的;limit 控制单次条数;max_tokens_budget 累计超即停(防成本失控)。
    返回 {scanned, filled, stopped, spent_tokens}。"""
    from app.services import long_sentence_service as lss
    r = await lss.backfill_paraphrase(db, limit=limit, only_missing=only_missing,
                                      max_tokens_budget=max_tokens_budget)
    return make_ok(r)


# ── 上传长难句:文字 → LLM 语法点 → 关联知识图谱 ────────────────────────────
@router.post("/long-sentences/upload-parse", response_model=BaseResponse[dict])
async def upload_parse_ls_api(body: dict, db: DbDep, admin: AdminDep):
    """粘贴文字 → LLM 抽语法点+例句,落 long_sentence 草稿(uploaded)。body={text, unit_id?}。"""
    from app.services import long_sentence_upload_service as lsu
    uid = body.get("unit_id")
    items = await lsu.parse_and_persist(
        db, text=(body.get("text") or ""), unit_id=uuid.UUID(str(uid)) if uid else None)
    await db.commit()
    return make_ok({"items": items})


@router.get("/long-sentences/uploaded", response_model=BaseResponse[dict])
async def list_uploaded_ls_api(db: DbDep, admin: AdminDep, limit: int = 50,
                               unit_id: uuid.UUID | None = None):
    """最近上传的长难句草稿(含已挂知识图谱节点)。unit_id 给定则只看该单元。"""
    from app.services import long_sentence_upload_service as lsu
    return make_ok({"items": await lsu.list_recent(db, limit=limit, unit_id=unit_id)})


@router.post("/long-sentences/uploaded/auto-link", response_model=BaseResponse[dict])
async def auto_link_uploaded_ls_api(body: dict, db: DbDep, admin: AdminDep):
    """一键关联:用语法点名分词打分,把该单元未挂的长难句自动挂到 cf/jf 最高分节点。body={unit_id}。"""
    from app.services import long_sentence_upload_service as lsu
    uid = body.get("unit_id")
    if not uid:
        raise AppError(code=400, message="缺少 unit_id")
    counts = await lsu.auto_link_unit(db, unit_id=uuid.UUID(str(uid)))
    await db.commit()
    items = await lsu.list_recent(db, limit=100, unit_id=uuid.UUID(str(uid)))
    return make_ok({"items": items, "counts": counts})


@router.post("/long-sentences/uploaded/{ls_id}/link-node", response_model=BaseResponse[dict])
async def link_uploaded_ls_node_api(ls_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """把该长难句的语法点挂靠到图谱已存在节点(限词法/句法)。"""
    from app.services import long_sentence_upload_service as lsu
    r = await lsu.link_node(db, ls_id=ls_id, node_id=uuid.UUID(str(body.get("node_id"))))
    await db.commit()
    return make_ok(r)


@router.post("/long-sentences/uploaded/{ls_id}/new-node", response_model=BaseResponse[dict])
async def new_uploaded_ls_node_api(ls_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """目录没有→在所选父分类下新建知识图谱节点并挂靠。"""
    from app.services import long_sentence_upload_service as lsu
    r = await lsu.new_node(db, ls_id=ls_id, parent_id=uuid.UUID(str(body.get("parent_id"))),
                           name=(body.get("name") or ""))
    await db.commit()
    return make_ok(r)


@router.delete("/long-sentences/uploaded/{ls_id}", response_model=BaseResponse[dict])
async def delete_uploaded_ls_api(ls_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """删除一条上传的长难句草稿(连带挂边)。"""
    from app.services import long_sentence_upload_service as lsu
    await lsu.delete_uploaded(db, ls_id=ls_id)
    await db.commit()
    return make_ok({"ok": True})


@router.get("/long-sentences", response_model=BaseResponse[LSAdminListOut])
async def list_long_sentences_api(
    db: DbDep, admin: AdminDep, status: str = "draft",
    node_id: uuid.UUID | None = None, skip: int = 0, limit: int = 20,
    sort_by: str = "created_at", order: str = "asc",
    source_kind: str | None = None, textbook_version: str | None = None,
    stage: str | None = None, grade: str | None = None, semester: str | None = None,
    exam_type: str | None = None,
):
    from app.services import long_sentence_service as lss
    rows, total = await lss.list_for_review(
        db, status=status, node_id=node_id, skip=skip, limit=limit, sort_by=sort_by, order=order,
        source_kind=source_kind, textbook_version=textbook_version, stage=stage,
        grade=grade, semester=semester, exam_type=exam_type)
    return make_ok(LSAdminListOut(total=total, items=[_to_ls_admin_item(r) for r in rows]))


@router.post("/long-sentences/{ls_id}/review", response_model=BaseResponse[LSAdminItem])
async def review_long_sentence_api(ls_id: uuid.UUID, body: ReviewRequest, db: DbDep, admin: AdminDep):
    from app.services import long_sentence_service as lss
    ls = await lss.review(db, ls_id=ls_id, approve=body.approve)
    await db.commit()
    return make_ok(_to_ls_admin_item(ls))


@router.get("/long-sentences/config", response_model=BaseResponse[LSConfigOut])
async def get_ls_config_api(db: DbDep, admin: AdminDep):
    from app.services import long_sentence_service as lss
    return make_ok(LSConfigOut(**await lss.get_config(db)))


@router.put("/long-sentences/config", response_model=BaseResponse[LSConfigOut])
async def set_ls_config_api(body: LSConfigIn, db: DbDep, admin: AdminDep):
    from app.services import long_sentence_service as lss
    cfg = await lss.set_config(db, updated_by=admin.id, sources=body.sources, verify_types=body.verify_types,
                               min_words=body.min_words, required_pass=body.required_pass,
                               textbook_difficulty_min=body.textbook_difficulty_min,
                               textbook_top_n=body.textbook_top_n)
    await db.commit()
    return make_ok(LSConfigOut(**cfg))


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
    GenJobCreatedOut, GenJobOut,
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
    if len(raw) > 300 * 1024 * 1024:  # 300 MB 上限(整本教材 PDF)
        raise AppError(code=400, message="PDF 文件过大（上限 300 MB）")

    file_id = pdf_upload_service.save_upload(raw)

    try:
        pages = pdf_upload_service.extract_pages(file_id)
    except Exception as exc:
        pdf_upload_service.delete_upload(file_id)
        raise AppError(code=422, message=f"PDF 文本提取失败：{exc}") from exc

    # 扫描件检测:无文字层(>90% 页空文本)→ 抽不出文字,识别/生成都会失败,需文字版或 OCR
    empty = sum(1 for p in pages if not (p or "").strip())
    is_scanned = bool(pages) and empty >= max(1, int(len(pages) * 0.9))

    segments_raw = pdf_upload_service.auto_detect_units(pages)
    auto_ok = segments_raw is not None

    return make_ok(PdfUploadOut(
        file_id=file_id,
        filename=file.filename,
        total_pages=len(pages),
        auto_split_success=auto_ok,
        auto_segments=[UnitSegment(**s) for s in (segments_raw or [])],
        page_offset=pdf_upload_service.detect_page_offset(pages),
        is_scanned=is_scanned,
    ))


@router.post("/curriculum/pdf/{file_id}/ocr", response_model=BaseResponse[dict])
async def start_pdf_ocr_api(file_id: str, admin: AdminDep):
    """启动扫描件 PDF 的 OCR(后台逐页豆包视觉识别)。前端轮询 /ocr-status。"""
    from app.services import pdf_ocr_job_service as ocr
    job = ocr.start_ocr(file_id)
    return make_ok({"status": job["status"], "done": job["done"], "total": job["total"]})


@router.get("/curriculum/pdf/{file_id}/ocr-status", response_model=BaseResponse[dict])
async def pdf_ocr_status_api(file_id: str, admin: AdminDep):
    """查询 OCR 进度;done 时返回基于 OCR 文字检测到的单元 segments。"""
    from app.services import pdf_ocr_job_service as ocr
    from app.schemas.pdf_upload import UnitSegment as _Seg
    job = ocr.get_status(file_id)
    if job is None:
        return make_ok({"status": "none", "done": 0, "total": 0, "segments": []})
    return make_ok({
        "status": job["status"], "done": job["done"], "total": job["total"],
        "error": job.get("error", ""),
        "segments": [_Seg(**s).model_dump() for s in (job.get("segments") or [])],
    })


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


def _to_gen_job_out(job) -> GenJobOut:
    return GenJobOut(
        job_id=job.id, source=job.source, textbook_version=job.textbook_version,
        grade=job.grade, semester=job.semester, status=job.status,
        total=job.total, done=job.done, failed=job.failed,
        created_at=job.created_at.isoformat() if job.created_at else None,
        results=[UnitGenerateResult(**r) for r in (job.results or [])],
    )


@router.post("/curriculum/pdf/{file_id}/generate",
             response_model=BaseResponse[GenJobCreatedOut])
async def generate_from_pdf(
    file_id: str,
    body: GenerateFromPdfRequest,
    db: DbDep,
    admin: AdminDep,
):
    """异步生成(方案 A):建任务并存待生成单元,**秒回 job_id**;后台逐单元生成
    (每单元独立 commit + 失败重试),前端轮询 /pdf-jobs/{job_id} 看进度,可关窗口。"""
    from app.services import curriculum_gen_service as gen
    try:
        pdf_upload_service.extract_pages(file_id)  # 验证文件存在
    except FileNotFoundError:
        raise AppError(code=404, message=f"PDF 不存在（file_id={file_id}），请重新上传")

    segments = [s.model_dump() for s in body.segments]
    job = await gen.create_job(
        db, source="pdf", file_id=file_id, textbook_version=body.textbook_version,
        grade=body.grade, semester=body.semester, content_status=body.content_status,
        segments=segments,
    )
    await db.commit()
    gen.schedule(job.id)
    return make_ok(GenJobCreatedOut(job_id=job.id, total=len(segments)))


@router.get("/curriculum/pdf-jobs/{job_id}", response_model=BaseResponse[GenJobOut])
async def get_gen_job(job_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """查生成任务进度(前端轮询)。"""
    from app.services import curriculum_gen_service as gen
    job = await gen.get_job(db, job_id)
    if job is None:
        raise AppError(code=404, message="生成任务不存在")
    return make_ok(_to_gen_job_out(job))


@router.post("/curriculum/pdf-jobs/{job_id}/retry", response_model=BaseResponse[GenJobOut])
async def retry_gen_job(job_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """重试生成任务:只重跑失败的单元(已成功的跳过)。文字版/扫描版均可。"""
    from app.services import curriculum_gen_service as gen
    ok = await gen.retry_job(db, job_id)
    if not ok:
        raise AppError(code=404, message="生成任务不存在")
    job = await gen.get_job(db, job_id)
    return make_ok(_to_gen_job_out(job))


@router.get("/curriculum/pdf-jobs", response_model=BaseResponse[dict])
async def list_gen_jobs(
    db: DbDep, admin: AdminDep, status: str | None = None,
    textbook_version: str | None = None, grade: str | None = None,
    semester: str | None = None, skip: int = 0, limit: int = 20,
):
    """列任务(供重开页面时重新挂上在跑的进度:status=running + 教材筛选)。分页返回。"""
    from app.services import curriculum_gen_service as gen
    jobs, total = await gen.list_jobs(db, status=status, textbook_version=textbook_version,
                                      grade=grade, semester=semester, skip=skip, limit=limit)
    return make_ok({"total": total, "items": [_to_gen_job_out(j).model_dump() for j in jobs]})


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


# ─── 电销 CRM(域23 · 平台自用)──────────────────────────────────────────────

def _lead_json(lead) -> dict:
    return SalesLeadOut.model_validate(lead).model_dump(mode="json")


@router.get("/sales/leads", response_model=BaseResponse[dict])
async def sales_list_leads(
    db: DbDep, admin: AdminDep,
    pool: str | None = None, status: str | None = None, source: str | None = None,
    region_code: str | None = None, mine: bool = False, dnc: bool | None = None,
    has_phone: bool | None = None,
    due: bool = False, sla: bool = False, tag: str | None = None,
    q: str | None = None, skip: int = 0, limit: int = 20,
):
    """线索分页列表。mine=只看自己私海;due=到期待办;sla=SLA 违约;tag=标签;has_phone=有/无电话;座席自动限权。"""
    from app.services import sales_crm_service as crm
    seat = await crm.seat_scope_for(db, admin.id)   # 座席只看公海+自己私海
    rows, total = await crm.list_leads(
        db, pool=pool, status=status, source=source, region_code=region_code,
        owner_admin_id=(admin.id if mine else None), dnc=dnc, has_phone=has_phone,
        due=due, sla=sla, tag=tag, seat_admin_id=seat, q=q, skip=skip, limit=limit)
    return make_ok({"total": total, "items": [_lead_json(r) for r in rows]})


@router.post("/sales/leads", response_model=BaseResponse[dict])
async def sales_create_lead(body: SalesLeadCreate, db: DbDep, admin: AdminDep):
    """手动录入线索(地区走 region_service 反解)。"""
    from app.services import sales_crm_service as crm
    lead = await crm.create_lead(db, data=body.model_dump(exclude_none=True))
    await db.commit()
    return make_ok(_lead_json(lead))


@router.post("/sales/leads/import", response_model=BaseResponse[dict])
async def sales_import_leads(body: SalesLeadImport, db: DbDep, admin: AdminDep):
    """批量导入线索(按 phone 去重)。"""
    from app.services import sales_crm_service as crm
    res = await crm.import_leads(
        db, items=[it.model_dump(exclude_none=True) for it in body.items], source=body.source)
    await db.commit()
    return make_ok(res)


@router.post("/sales/leads/ingest", response_model=BaseResponse[dict])
async def sales_ingest_leads(body: SalesLeadIngest, db: DbDep, admin: AdminDep):
    """采集→入库通用适配器:{名称,电话,地址,主营业务,城市} 列表 → 解析城市为区划码 + 归一 →
    按 phone 去重入库。数据来自百度地图 API / 探迹 / Excel 均走此口。source_note 记合规来源。"""
    from app.services import sales_crm_service as crm
    res = await crm.ingest_external_leads(
        db, items=[it.model_dump() for it in body.items],
        source=body.source, source_note=body.source_note, require_phone=body.require_phone)
    await db.commit()
    return make_ok(res)


# ── 百度地图获客(官方 Place API;AK 走配置;额度用尽即停)──────────────────
@router.get("/sales/baidu/ak", response_model=BaseResponse[dict])
async def sales_baidu_ak_get(db: DbDep, admin: AdminDep):
    from app.services import baidu_lead_service as bd
    ak = await bd.get_ak(db)
    return make_ok({"ak_set": bool(ak), "ak_masked": bd.mask_ak(ak)})


@router.put("/sales/baidu/ak", response_model=BaseResponse[dict])
async def sales_baidu_ak_set(body: BaiduAkIn, db: DbDep, admin: AdminDep):
    from app.services import baidu_lead_service as bd
    await bd.set_ak(db, ak=body.ak, updated_by=admin.id)
    await db.commit()
    return make_ok({"ak_masked": bd.mask_ak(await bd.get_ak(db))})


@router.post("/sales/baidu/fetch", response_model=BaseResponse[dict])
async def sales_baidu_fetch(body: BaiduFetchIn, db: DbDep, admin: AdminDep):
    """按 城市(+区县)+ 关键词 调官方百度 Place API 检索 POI;ingest=true 直接入库(按 phone 去重)。
    额度用尽自动停(返回 quota_stopped=True)。"""
    from app.services import baidu_lead_service as bd
    res = await bd.fetch_and_ingest(
        db, region_name=body.region_name, districts=body.districts,
        keywords=body.keywords, pages=body.pages, ingest=body.ingest)
    await db.commit()   # 预览也提交:留住 map_usage 日用量计数(预览同样消耗真实配额)
    return make_ok(res)


# ── 高德地图获客(官方 POI 文本检索;Key 走配置;额度用尽即停)────────────────
@router.get("/sales/amap/ak", response_model=BaseResponse[dict])
async def sales_amap_key_get(db: DbDep, admin: AdminDep):
    from app.services import amap_lead_service as am
    k = await am.get_key(db)
    return make_ok({"ak_set": bool(k), "ak_masked": am.mask_key(k)})


@router.put("/sales/amap/ak", response_model=BaseResponse[dict])
async def sales_amap_key_set(body: BaiduAkIn, db: DbDep, admin: AdminDep):
    from app.services import amap_lead_service as am
    await am.set_key(db, key=body.ak, updated_by=admin.id)
    await db.commit()
    return make_ok({"ak_masked": am.mask_key(await am.get_key(db))})


@router.post("/sales/amap/fetch", response_model=BaseResponse[dict])
async def sales_amap_fetch(body: BaiduFetchIn, db: DbDep, admin: AdminDep):
    """按 城市(+区县)+ 关键词 调官方高德 POI 检索;ingest=true 直接入库(按 phone 去重)。额度用尽自动停。"""
    from app.services import amap_lead_service as am
    res = await am.fetch_and_ingest(
        db, region_name=body.region_name, districts=body.districts,
        keywords=body.keywords, types=body.types, pages=body.pages, ingest=body.ingest)
    await db.commit()   # 预览也提交:留住 map_usage 日用量计数(预览同样消耗真实配额)
    return make_ok(res)


# ── 地图获客:每日查询次数限额 + 用量 ─────────────────────────────────────────
class _MapQuotaIn(BaseModel):
    baidu: int | None = None
    amap: int | None = None


@router.get("/sales/map/usage", response_model=BaseResponse[dict])
async def sales_map_usage(db: DbDep, admin: AdminDep):
    """各数据源今日已用/每日上限/剩余(按东八区自然日)。"""
    from app.services import map_usage_service as usage
    return make_ok(await usage.get_usage(db))


@router.put("/sales/map/quota", response_model=BaseResponse[dict])
async def sales_map_quota(body: _MapQuotaIn, db: DbDep, admin: AdminDep):
    """设置每日查询次数上限(百度/高德各自)。"""
    from app.services import map_usage_service as usage
    cfg = await usage.set_quota(db, quota=body.model_dump(exclude_none=True), updated_by=admin.id)
    await db.commit()
    return make_ok(cfg)


@router.patch("/sales/leads/{lead_id}", response_model=BaseResponse[dict])
async def sales_update_lead(lead_id: uuid.UUID, body: SalesLeadUpdate, db: DbDep, admin: AdminDep):
    """改线索(状态/DNC/consent/下次跟进/意向分/地区等)。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    patch = body.model_dump(exclude_unset=True)
    old_status = (await crm.get_lead(db, lead_id)).status
    lead = await crm.update_lead(db, lead_id=lead_id, patch=patch)
    if patch.get("status") and lead.status != old_status:
        await audit.record(db, admin_id=admin.id, action="status_change", lead_id=lead_id,
                           detail={"before": old_status, "after": lead.status})
    if "dnc" in patch:
        await audit.record(db, admin_id=admin.id, action="dnc", lead_id=lead_id,
                           detail={"dnc": lead.dnc})
    await db.commit()
    return make_ok(_lead_json(lead))


@router.post("/sales/leads/{lead_id}/claim", response_model=BaseResponse[dict])
async def sales_claim_lead(lead_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """认领进私海(防撞单:已被他人认领则 409)。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    lead = await crm.claim_lead(db, lead_id=lead_id, admin_id=admin.id)
    await audit.record(db, admin_id=admin.id, action="claim", lead_id=lead_id)
    await db.commit()
    return make_ok(_lead_json(lead))


@router.post("/sales/leads/{lead_id}/release", response_model=BaseResponse[dict])
async def sales_release_lead(lead_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """退回公海。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    lead = await crm.release_lead(db, lead_id=lead_id)
    await audit.record(db, admin_id=admin.id, action="release", lead_id=lead_id)
    await db.commit()
    return make_ok(_lead_json(lead))


@router.get("/sales/seats", response_model=BaseResponse[list])
async def sales_seats(db: DbDep, admin: AdminDep):
    """座席列表(平台管理员),供批量派单选人。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.list_seats(db))


@router.post("/sales/leads/assign", response_model=BaseResponse[dict])
async def sales_batch_assign(body: BatchAssignIn, db: DbDep, admin: AdminDep):
    """批量派单/认领:owner_admin_id 指定座席,缺省则认领给自己。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    owner = body.owner_admin_id or admin.id
    n = await crm.batch_assign(db, lead_ids=body.lead_ids, owner_admin_id=owner)
    for lid in body.lead_ids:
        await audit.record(db, admin_id=admin.id, action="assign", lead_id=lid,
                           detail={"owner_admin_id": str(owner)})
    await db.commit()
    return make_ok({"assigned": n})


@router.post("/sales/leads/auto-assign", response_model=BaseResponse[dict])
async def sales_auto_assign(body: AutoAssignIn, db: DbDep, admin: AdminDep):
    """自动分配:把公海线索(排除 DNC,可按地区)轮询派给选定座席。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    res = await crm.auto_assign(db, seat_ids=body.seat_ids, count=body.count, region_code=body.region_code)
    for lid in res.get("lead_ids", []):
        await audit.record(db, admin_id=admin.id, action="auto_assign", lead_id=uuid.UUID(lid))
    await db.commit()
    return make_ok({"assigned": res["assigned"], "by_seat": res["by_seat"]})


@router.get("/sales/leaderboard", response_model=BaseResponse[list])
async def sales_leaderboard(db: DbDep, admin: AdminDep, days: int = 7):
    """座席业绩排行:私海线索/期内拨打·接通/成交/转化率。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.seat_leaderboard(db, days=days))


@router.get("/sales/audit", response_model=BaseResponse[dict])
async def sales_audit_list(
    db: DbDep, admin: AdminDep, lead_id: uuid.UUID | None = None,
    admin_id: uuid.UUID | None = None, action: str | None = None,
    skip: int = 0, limit: int = 30,
):
    """操作审计日志(可按线索/座席/动作筛选,分页)。"""
    from app.services import sales_audit_service as audit
    rows, total = await audit.list_audit(
        db, lead_id=lead_id, admin_id=admin_id, action=action, skip=skip, limit=limit)
    return make_ok({"total": total, "items": [
        {"id": str(r.id), "admin_id": str(r.admin_id) if r.admin_id else None,
         "action": r.action, "lead_id": str(r.lead_id) if r.lead_id else None,
         "detail": r.detail, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows]})


@router.get("/sales/leads/{lead_id}/activities", response_model=BaseResponse[dict])
async def sales_list_activities(
    lead_id: uuid.UUID, db: DbDep, admin: AdminDep, skip: int = 0, limit: int = 20,
):
    """线索跟进时间线(分页)。"""
    from app.services import sales_crm_service as crm
    rows, total = await crm.list_activities(db, lead_id=lead_id, skip=skip, limit=limit)
    return make_ok({"total": total,
                    "items": [ActivityOut.model_validate(r).model_dump(mode="json") for r in rows]})


@router.post("/sales/leads/{lead_id}/activities", response_model=BaseResponse[dict])
async def sales_add_activity(
    lead_id: uuid.UUID, body: ActivityCreate, db: DbDep, admin: AdminDep,
):
    """加一条跟进记录(顺带更新最后触达/下次跟进/状态)。"""
    from app.services import sales_crm_service as crm
    act = await crm.add_activity(
        db, lead_id=lead_id, admin_id=admin.id, channel=body.channel,
        content=body.content, direction=body.direction, outcome=body.outcome,
        next_follow_at=body.next_follow_at, status=body.status)
    await db.commit()
    return make_ok(ActivityOut.model_validate(act).model_dump(mode="json"))


@router.get("/sales/recommend", response_model=BaseResponse[dict])
async def sales_recommend(db: DbDep, admin: AdminDep, skip: int = 0, limit: int = 20):
    """赢单画像反查推荐:用 won 线索画像给公海新线索打分排序(分页)。"""
    from app.services import sales_crm_service as crm
    rows, total = await crm.recommend(db, skip=skip, limit=limit)
    await db.commit()   # 写回 similar_score
    return make_ok({"total": total, "items": [_lead_json(r) for r in rows]})


@router.get("/sales/board", response_model=BaseResponse[dict])
async def sales_board(db: DbDep, admin: AdminDep):
    """座席看板:线索分布 + 今日拨打量/接通率/今日新增 + 我的待办数。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.board_stats(db, admin_id=admin.id))


@router.post("/sales/recycle-public-pool", response_model=BaseResponse[dict])
async def sales_recycle_pool(db: DbDep, admin: AdminDep):
    """手动触发公海回收(私海超 N 天未跟进 → 公海;N 读 system_configs)。"""
    from app.services import sales_crm_service as crm
    n = await crm.recycle_public_pool(db)
    await db.commit()
    return make_ok({"recycled": n})


# ─── 电销 CRM · P1 意向分析 / 呼叫接入位 ──────────────────────────────────────

@router.post("/sales/leads/{lead_id}/call-record", response_model=BaseResponse[dict])
async def sales_call_record(lead_id: uuid.UUID, body: CallRecordIn, db: DbDep, admin: AdminDep):
    """呼叫中心接入位:回传一通电话(录音/转写/时长)→ 落 call 跟进,有转写则跑意向分析回填。"""
    from app.services import sales_analysis_service as ana
    act = await ana.ingest_call_record(
        db, lead_id=lead_id, admin_id=admin.id, recording_url=body.recording_url,
        asr_text=body.asr_text, call_duration_sec=body.call_duration_sec,
        direction=body.direction, outcome=body.outcome, content=body.content)
    await db.commit()
    return make_ok(ActivityOut.model_validate(act).model_dump(mode="json"))


@router.post("/sales/activities/{activity_id}/analyze", response_model=BaseResponse[dict])
async def sales_analyze_activity(activity_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """对一条已有转写的跟进记录(重新)跑意向分析,回填 activity + 线索。"""
    from app.services import sales_analysis_service as ana
    act = await ana.analyze_activity(db, activity_id=activity_id)
    await db.commit()
    return make_ok(ActivityOut.model_validate(act).model_dump(mode="json"))


@router.post("/sales/analyze", response_model=BaseResponse[dict])
async def sales_analyze_text(body: AnalyzeTextIn, db: DbDep, admin: AdminDep):
    """试跑:任意转写文本 → 意向分析 schema(不落库)。"""
    from app.services import sales_analysis_service as ana
    return make_ok(await ana.analyze_transcript(body.text, source=body.source))


# ─── 电销 CRM · P2 企微会话存档 ───────────────────────────────────────────────

@router.get("/sales/wecom/config", response_model=BaseResponse[dict])
async def sales_wecom_config(db: DbDep, admin: AdminDep):
    """企微会话存档接入配置(开关/corpid/游标;secret/私钥走 env,不在此)。"""
    from app.services import wecom_archive_service as wa
    return make_ok(await wa.get_config(db))


@router.put("/sales/wecom/config", response_model=BaseResponse[dict])
async def sales_wecom_config_update(body: WecomConfigUpdate, db: DbDep, admin: AdminDep):
    from app.services import wecom_archive_service as wa
    cfg = await wa.update_config(db, patch=body.model_dump(exclude_unset=True), updated_by=admin.id)
    await db.commit()
    return make_ok(cfg)


@router.post("/sales/wecom/ingest", response_model=BaseResponse[dict])
async def sales_wecom_ingest(body: WecomIngestIn, db: DbDep, admin: AdminDep):
    """接入位:喂一批**已解密**企微消息 → 去重入库 + 按 external_userid 关联线索 + 文本触发意向分析。"""
    from app.services import wecom_archive_service as wa
    res = await wa.ingest_messages(
        db, messages=[m.model_dump() for m in body.items], run_analysis=body.run_analysis)
    await db.commit()
    return make_ok(res)


@router.post("/sales/wecom/pull", response_model=BaseResponse[dict])
async def sales_wecom_pull(db: DbDep, admin: AdminDep):
    """真·拉取(GetChatData→解密→入库)。未接入原生 SDK 时返回 501 说明。"""
    from app.services import wecom_archive_service as wa
    try:
        res = await wa.pull_via_sdk(db)
        await db.commit()
        return make_ok(res)
    except NotImplementedError as exc:
        raise AppError(code=501, message=str(exc))


@router.get("/sales/leads/{lead_id}/wecom", response_model=BaseResponse[dict])
async def sales_lead_wecom(lead_id: uuid.UUID, db: DbDep, admin: AdminDep,
                          skip: int = 0, limit: int = 50):
    """某线索的企微会话记录(分页)。"""
    from app.services import wecom_archive_service as wa
    rows, total = await wa.list_lead_messages(db, lead_id=lead_id, skip=skip, limit=limit)
    return make_ok({"total": total,
                    "items": [WecomMsgOut.model_validate(r).model_dump(mode="json") for r in rows]})


# ─── 电销 CRM · 打磨:来源统计 / 查重合并 / Excel 导入 ─────────────────────────

@router.get("/sales/source-stats", response_model=BaseResponse[list])
async def sales_source_stats(db: DbDep, admin: AdminDep):
    """线索来源统计:各来源线索数 / 成交数 / 转化率。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.source_stats(db))


@router.get("/sales/duplicates", response_model=BaseResponse[list])
async def sales_duplicates(db: DbDep, admin: AdminDep, limit: int = 100):
    """按电话找重复线索组(供查重合并)。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.find_duplicate_groups(db, limit=limit))


@router.post("/sales/leads/merge", response_model=BaseResponse[dict])
async def sales_merge_leads(body: MergeLeadsIn, db: DbDep, admin: AdminDep):
    """合并重复线索:跟进/企微记录改挂到 survivor,补空字段 + 合并产品意见,删 dup。"""
    from app.services import sales_crm_service as crm, sales_audit_service as audit
    res = await crm.merge_leads(db, survivor_id=body.survivor_id, dup_ids=body.dup_ids)
    await audit.record(db, admin_id=admin.id, action="merge", lead_id=body.survivor_id,
                       detail={"dup_ids": [str(d) for d in body.dup_ids], "merged": res.get("merged")})
    await db.commit()
    return make_ok(res)


@router.post("/sales/leads/import-excel", response_model=BaseResponse[dict])
async def sales_import_excel(
    db: DbDep, admin: AdminDep,
    file: UploadFile = File(..., description="线索 Excel(.xlsx);表头含 名称/电话/城市/行业/来源说明"),
    source: str = Form("import"),
):
    """Excel 文件导入线索(首行表头,列名容忍),按 phone 去重。"""
    from app.services import sales_crm_service as crm
    content = await file.read()
    res = await crm.import_from_excel(db, content=content, source=source)
    await db.commit()
    return make_ok(res)


# ─── 电销 CRM · 打磨:配置 / 话术库 / 导出 ────────────────────────────────────

@router.get("/sales/config", response_model=BaseResponse[dict])
async def sales_get_config(db: DbDep, admin: AdminDep):
    """电销 CRM 配置(回收天数/SLA 小时/座席名单/标签建议 等)。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.get_config(db))


@router.put("/sales/config", response_model=BaseResponse[dict])
async def sales_update_config(body: SalesConfigUpdate, db: DbDep, admin: AdminDep):
    from app.services import sales_crm_service as crm
    cfg = await crm.update_config(db, patch=body.model_dump(exclude_unset=True), updated_by=admin.id)
    await db.commit()
    return make_ok(cfg)


@router.get("/sales/scripts", response_model=BaseResponse[list])
async def sales_get_scripts(db: DbDep, admin: AdminDep):
    """话术库 / 跟进 SOP。"""
    from app.services import sales_crm_service as crm
    return make_ok(await crm.get_scripts(db))


@router.put("/sales/scripts", response_model=BaseResponse[list])
async def sales_set_scripts(body: ScriptsIn, db: DbDep, admin: AdminDep):
    from app.services import sales_crm_service as crm
    res = await crm.set_scripts(db, scripts=[s.model_dump() for s in body.scripts], updated_by=admin.id)
    await db.commit()
    return make_ok(res)


@router.get("/sales/leads/export")
async def sales_export_leads(
    db: DbDep, admin: AdminDep,
    pool: str | None = None, status: str | None = None, source: str | None = None,
    region_code: str | None = None, mine: bool = False, dnc: bool | None = None,
    due: bool = False, sla: bool = False, tag: str | None = None, q: str | None = None,
):
    """按当前筛选导出线索为 .xlsx(座席自动限权,最多 5000 条)。"""
    from fastapi.responses import Response
    from app.services import sales_crm_service as crm
    seat = await crm.seat_scope_for(db, admin.id)
    data = await crm.export_leads_xlsx(
        db, pool=pool, status=status, source=source, region_code=region_code,
        owner_admin_id=(admin.id if mine else None), dnc=dnc, due=due, sla=sla, tag=tag,
        seat_admin_id=seat, q=q)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales_leads.xlsx"})
