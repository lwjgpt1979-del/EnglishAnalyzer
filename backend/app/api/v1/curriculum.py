"""V2 课程浏览 API（D-079 / M2）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.services import curriculum_service

router = APIRouter(prefix="/curriculum", tags=["curriculum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/units")
async def list_units(
    db: DbDep,
    current_user: UserDep,
    textbook_version: str = Query(...),
    grade: str = Query(...),
    semester: str = Query(..., description="上 / 下"),
):
    items = await curriculum_service.list_units(
        db,
        user_id=current_user.id,
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
    )
    return make_ok([i.model_dump(mode="json") for i in items])


@router.get("/units/{unit_id}")
async def get_unit_detail(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    detail = await curriculum_service.get_unit_detail(
        db, user_id=current_user.id, unit_id=unit_id,
    )
    return make_ok(detail.model_dump(mode="json"))


@router.get("/knowledge-points/{kp_id}/contents")
async def get_kp_contents(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    contents = await curriculum_service.get_kp_contents(
        db, user_id=current_user.id, kp_id=kp_id,
    )
    return make_ok([c.model_dump(mode="json") for c in contents])
