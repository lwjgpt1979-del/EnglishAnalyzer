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
    accuracy: float                 # 原始正确率 correct/total（兼容保留）
    mastery: float                  # 加权掌握度 0–1（展示口径）
    mastery_events: int             # 事件数 C；< 10 证据不足
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
    mastery: float      # 加权掌握度 0–1（当日日末值）
    mastery_events: int # 事件数 C


@router.get("/trend", response_model=BaseResponse[list[KpTrendPoint]])
async def get_kp_trend(
    db: DbDep,
    current_user: UserDep,
    node_id: uuid.UUID = Query(..., description="知识点 node_id（列表 kp_id）"),
    days: int = Query(30, ge=7, le=90, description="查询最近 N 天（7-90）"),
):
    """返回指定知识点近 N 天的日加权掌握度趋势（从 answer_log 重放，无需历史快照）。"""
    await get_rls_db(db, str(current_user.id))
    points = await kp_mastery_service.get_kp_mastery_trend(
        db, student_id=current_user.id, node_id=node_id, days=days
    )
    return make_ok([KpTrendPoint(**p) for p in points])
