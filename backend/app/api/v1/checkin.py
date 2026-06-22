"""学习打卡(通用):记录学习日 + 连续天数 + 月历。共享 StudyCheckin,不绑定具体功能。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import checkin_service

router = APIRouter(prefix="/checkin", tags=["checkin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=BaseResponse[dict])
async def checkin(db: DbDep, current_user: UserDep):
    """今日打卡(记录一个学习日,幂等)。返回 {checked_in_today, current_streak, longest_streak…}。"""
    await get_rls_db(db, str(current_user.id))
    await checkin_service.record_study_day(db, student_id=current_user.id)
    await db.commit()
    st = await checkin_service.get_checkin_status(db, student_id=current_user.id)
    return make_ok(st)


@router.get("/status", response_model=BaseResponse[dict])
async def status(db: DbDep, current_user: UserDep):
    """打卡状态:今日是否已打 + 当前连续 + 历史最高。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await checkin_service.get_checkin_status(db, student_id=current_user.id))


@router.get("/calendar", response_model=BaseResponse[dict])
async def calendar(
    db: DbDep, current_user: UserDep, year: int | None = None, month: int | None = None,
):
    """当月打卡日历:已打卡日列表 + 连续/最高天数。"""
    await get_rls_db(db, str(current_user.id))
    now = datetime.now(timezone.utc)
    return make_ok(await checkin_service.get_month_calendar(
        db, student_id=current_user.id, year=year or now.year, month=month or now.month))
