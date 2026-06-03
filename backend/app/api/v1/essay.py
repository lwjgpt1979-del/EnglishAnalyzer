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

router = APIRouter(prefix="/essays", tags=["essays"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


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
