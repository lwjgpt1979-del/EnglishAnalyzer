"""个人知识点掌握台账 API（M39 / M46）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import kp_mastery_service

router = APIRouter(prefix="/kp-mastery", tags=["kp-mastery"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class KpMasteryItem(BaseModel):
    kp_key: str
    kp_id: uuid.UUID | None
    kp_description: str | None      # 知识点简介
    correct_count: int
    wrong_count: int
    accuracy: float                 # correct / total，total=0 时为 0.0
    sources: list[str]              # 贡献来源，如 ['practice', 'paper_upload']
    last_activity_at: str | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=BaseResponse[list[KpMasteryItem]])
async def get_kp_mastery(db: DbDep, current_user: UserDep):
    """个人知识点掌握(KP-First:直读新表 student_kp,node 维度),按正确率升序(弱项在前)。"""
    await get_rls_db(db, str(current_user.id))
    rows = await kp_mastery_service.get_kp_mastery_nodes(db, student_id=current_user.id)
    return make_ok([KpMasteryItem(**r) for r in rows])


class KpTrendPoint(BaseModel):
    date: str           # YYYY-MM-DD
    accuracy: float
    correct_count: int
    wrong_count: int


@router.get("/trend", response_model=BaseResponse[list[KpTrendPoint]])
async def get_kp_trend(
    db: DbDep,
    current_user: UserDep,
    kp_key: str = Query(..., description="知识点名称"),
    days: int = Query(30, ge=7, le=90, description="查询最近 N 天（7-90）"),
):
    """返回指定知识点近 N 天的日正确率趋势（M46）。"""
    await get_rls_db(db, str(current_user.id))
    points = await kp_mastery_service.get_kp_trend(
        db, student_id=current_user.id, kp_key=kp_key, days=days
    )
    return make_ok([KpTrendPoint(**p) for p in points])
