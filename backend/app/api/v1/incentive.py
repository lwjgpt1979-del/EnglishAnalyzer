"""学习激励中心 API（M10）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.incentive import IncentiveSummaryOut
from app.services import incentive_service

router = APIRouter(prefix="/incentive", tags=["incentive"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/summary", response_model=BaseResponse[IncentiveSummaryOut])
async def get_incentive_summary(db: DbDep, current_user: UserDep):
    """返回当前学生的激励总览：等级/经验值 + 连续打卡 + 勋章 + 成就。"""
    await get_rls_db(db, str(current_user.id))
    data = await incentive_service.get_summary(db, student_id=current_user.id)
    return make_ok(data)
