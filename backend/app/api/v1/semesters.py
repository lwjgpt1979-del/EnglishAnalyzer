"""V2 学期会员 API（D-079 / M1）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.semesters import PurchasedSemesterOut
from app.services import semester_service

router = APIRouter(prefix="/semesters", tags=["semesters"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/mine", response_model=BaseResponse[list[PurchasedSemesterOut]])
async def list_mine(db: DbDep, current_user: UserDep):
    """返回当前用户已购学期会员列表（按到期时间倒序）。"""
    await get_rls_db(db, str(current_user.id))
    items = await semester_service.list_my_semesters(db, user_id=current_user.id)
    return make_ok([
        PurchasedSemesterOut(
            id=ps.id,
            textbook_version=ps.textbook_version,
            grade=ps.grade,
            semester=str(ps.semester),
            tier=str(ps.tier),
            started_at=ps.started_at,
            expires_at=ps.expires_at,
        ) for ps in items
    ])
