"""会员状态 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.payments import CurrentMembershipOut
from app.services import membership_service

router = APIRouter(prefix="/memberships", tags=["memberships"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=BaseResponse[CurrentMembershipOut])
async def get_my_membership(db: DbDep, current_user: UserDep):
    """返回当前用户的会员状态。无付费会员则返回 tier=free。"""
    await get_rls_db(db, str(current_user.id))
    membership = await membership_service.get_active_membership(
        db, user_id=current_user.id
    )
    if membership is None:
        return make_ok(CurrentMembershipOut())
    return make_ok(CurrentMembershipOut.model_validate(membership))
