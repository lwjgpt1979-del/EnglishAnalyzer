"""作文精修 API（D-109）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d5_learning import Essay
from app.schemas.base import BaseResponse, make_ok
from app.schemas.essay import (
    EssayCreate, EssayListItem, EssayListOut, EssayOut,
    EssayProgressOut, EssayRoundItem, EssayTemplatesOut, RepolishIn,
)
from app.services import essay_service, membership_service

from pydantic import BaseModel, Field

router = APIRouter(prefix="/essays", tags=["essays"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


def _stage(user: User) -> str:
    g = getattr(user, "preferred_grade", None) or ""
    if "高中" in g:
        return "senior"
    if "小学" in g:
        return "primary"
    return "junior"


# ── 应试训练 E1 ────────────────────────────────────────────────────────────────
@router.get("/prompts", response_model=BaseResponse[list])
async def list_essay_prompts(db: DbDep, current_user: UserDep,
                             stage: str | None = None, genre: str | None = None):
    """作文题库：按学段/体裁列题（含必答要点/人称/时态/词数）。"""
    rows = await essay_service.list_prompts(db, stage=stage or _stage(current_user), genre=genre)
    return make_ok([{
        "id": str(p.id), "stage": p.stage, "genre": p.genre, "title": p.title,
        "scenario": p.scenario, "required_points": p.required_points,
        "person": p.person, "tense": p.tense, "word_min": p.word_min, "word_max": p.word_max,
    } for p in rows])


class AnalyzePromptIn(BaseModel):
    prompt_id: uuid.UUID | None = None
    text: str | None = None


@router.post("/analyze-prompt", response_model=BaseResponse[dict])
async def analyze_prompt_api(body: AnalyzePromptIn, db: DbDep, current_user: UserDep):
    """审题助手：抽取要点清单 + 人称/时态/词数。"""
    return make_ok(await essay_service.analyze_prompt(
        db, prompt_id=body.prompt_id, text=body.text))


class DiagnoseIn(BaseModel):
    draft_text: str = Field(..., min_length=1)
    prompt_id: uuid.UUID | None = None
    prompt_text: str | None = None
    timed_seconds: int | None = None


@router.post("/diagnose", response_model=BaseResponse[dict])
async def diagnose_api(body: DiagnoseIn, db: DbDep, current_user: UserDep):
    """按档诊断：三维+档次 + 漏点检测 + 升档建议 + 错因沉淀。"""
    await get_rls_db(db, str(current_user.id))
    essay = await essay_service.diagnose_essay(
        db, student_id=current_user.id, draft_text=body.draft_text,
        prompt_id=body.prompt_id, prompt_text=body.prompt_text,
        stage=_stage(current_user), timed_seconds=body.timed_seconds)
    await db.commit()
    return make_ok({"id": str(essay.id), **(essay.dimensions or {})})


@router.get("/error-log", response_model=BaseResponse[dict])
async def essay_error_log_api(db: DbDep, current_user: UserDep):
    """作文写作错因本：按类型聚合 + 最近明细。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await essay_service.error_log_summary(db, student_id=current_user.id))


def _to_out(e: Essay) -> EssayOut:
    dim = e.dimensions or {}
    rounds = dim.get("rounds") or []
    return EssayOut(
        id=e.id, original_text=e.original_text, polished_text=e.polished_text,
        scores=dim.get("scores", []), total=dim.get("total", 0),
        issues=dim.get("issues", []), title=dim.get("title"),
        essay_type=dim.get("essay_type"), round_count=e.round_count,
        status=str(e.status), created_at=e.created_at.isoformat(),
        rounds=[EssayRoundItem(round=i + 1, total=r.get("total", 0)) for i, r in enumerate(rounds)],
    )


@router.post("", response_model=BaseResponse[EssayOut])
async def create_essay(body: EssayCreate, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    essay = await essay_service.polish_essay(
        db, student_id=current_user.id, original_text=body.original_text,
        title=body.title, essay_type=body.essay_type, wrong_question_id=body.wrong_question_id)
    await db.commit()
    return make_ok(_to_out(essay))


@router.get("", response_model=BaseResponse[EssayListOut])
async def list_my_essays(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    rows = await essay_service.list_essays(db, student_id=current_user.id)
    items = [
        EssayListItem(
            id=e.id, title=(e.dimensions or {}).get("title"),
            essay_type=(e.dimensions or {}).get("essay_type"),
            total=(e.dimensions or {}).get("total", 0),
            status=str(e.status), created_at=e.created_at.isoformat(),
        )
        for e in rows
    ]
    return make_ok(EssayListOut(total=len(items), items=items))


@router.get("/templates", response_model=BaseResponse[EssayTemplatesOut])
async def essay_templates(db: DbDep, current_user: UserDep, essay_type: str | None = None):
    await get_rls_db(db, str(current_user.id))
    m = await membership_service.get_active_membership(db, user_id=current_user.id)
    tier = str(m.tier) if m else "free"
    t = await essay_service.get_configured_templates(db, essay_type, tier=tier)
    return make_ok(EssayTemplatesOut(essay_type=essay_type, template=t["template"], samples=t["samples"]))


@router.get("/compose-templates", response_model=BaseResponse[dict])
async def compose_templates_api(db: DbDep, current_user: UserDep, genre: str | None = None):
    """搭作文:某体裁的模版列表(多模版×分段×候选句)。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok({"templates": await essay_service.compose_templates(db, genre=genre)})


@router.post("/adapt-sentences", response_model=BaseResponse[dict])
async def adapt_sentences_api(body: dict, db: DbDep, current_user: UserDep):
    """把你学过的长难句适配到各段功能(LLM,结果缓存)。body: {genre, scenario, slots:[{key,label}]}。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await essay_service.adapt_sentences(
        db, student_id=current_user.id, genre=body.get("genre"),
        scenario=str(body.get("scenario") or ""), slots=body.get("slots") or []))


@router.post("/upgrade", response_model=BaseResponse[dict])
async def upgrade_sentences_api(body: dict, db: DbDep, current_user: UserDep):
    """逐句升级:平句→高分句,优先套用你学过的长难句。body: {draft_text, genre?}。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await essay_service.upgrade_sentences(
        db, student_id=current_user.id,
        draft_text=str(body.get("draft_text") or ""), essay_type=body.get("genre")))


@router.get("/scaffold", response_model=BaseResponse[dict])
async def writing_scaffold(db: DbDep, current_user: UserDep, genre: str | None = None):
    """写作页支架:模版骨架 + 高分句 + 你学过的长难句(按体裁取)。"""
    await get_rls_db(db, str(current_user.id))
    m = await membership_service.get_active_membership(db, user_id=current_user.id)
    tier = str(m.tier) if m else "free"
    return make_ok(await essay_service.writing_scaffold(
        db, student_id=current_user.id, essay_type=genre, tier=tier))


@router.get("/progress", response_model=BaseResponse[EssayProgressOut])
async def my_progress(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    return make_ok(EssayProgressOut(**await essay_service.get_progress(db, student_id=current_user.id)))


@router.post("/{essay_id}/repolish", response_model=BaseResponse[EssayOut])
async def repolish(essay_id: uuid.UUID, body: RepolishIn, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    essay = await essay_service.repolish_essay(
        db, student_id=current_user.id, essay_id=essay_id, revised_text=body.revised_text)
    await db.commit()
    return make_ok(_to_out(essay))


@router.get("/{essay_id}", response_model=BaseResponse[EssayOut])
async def get_my_essay(essay_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    e = await essay_service.get_essay(db, student_id=current_user.id, essay_id=essay_id)
    if e is None:
        raise AppError(code=404, message="作文记录不存在")
    return make_ok(_to_out(e))
