from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.users import UserMeOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=BaseResponse[UserMeOut])
async def get_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """返回当前登录用户的基本信息，同时注入 RLS 会话变量。

    RLS 注入：SET LOCAL app.current_user_id = <user_id>
    Tech Spec §2：所有受保护接口必须注入此变量。
    """
    await get_rls_db(db, str(current_user.id))

    # 计算冷静期剩余天数
    days_until_cancellation: int | None = None
    if current_user.deactivation_scheduled_at is not None:
        scheduled_at = current_user.deactivation_scheduled_at
        now = datetime.now(timezone.utc)
        days_until_cancellation = max(0, (scheduled_at - now).days)

    return make_ok(
        UserMeOut(
            id=str(current_user.id),
            role=current_user.role,
            nickname=current_user.nickname,
            avatar_url=current_user.avatar_url,
            is_active=current_user.is_active,
            phone=current_user.phone,
            profile_completed=current_user.profile_completed,
            birth_year=current_user.birth_year,
            deactivation_scheduled_at=current_user.deactivation_scheduled_at,
            days_until_cancellation=days_until_cancellation,
        )
    )
