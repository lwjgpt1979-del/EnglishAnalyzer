"""个性化每日学习计划 API（M9）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.learning_plan import TodayPlanOut
from app.services import learning_plan_service

router = APIRouter(prefix="/learning-plan", tags=["learning-plan"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/today", response_model=BaseResponse[TodayPlanOut])
async def get_today_plan(db: DbDep, current_user: UserDep):
    """返回当前学生的今日个性化学习计划（基于掌握台账弱项 + 当日活动）。"""
    await get_rls_db(db, str(current_user.id))
    plan = await learning_plan_service.get_today_plan(db, student_id=current_user.id)
    return make_ok(plan)
