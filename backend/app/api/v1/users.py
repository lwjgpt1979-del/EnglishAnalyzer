from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.auth import UserProfileOut
from app.schemas.base import BaseResponse, make_ok

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=BaseResponse[UserProfileOut])
async def get_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """返回当前登录用户的基本信息，同时注入 RLS 会话变量。

    RLS 注入：SET LOCAL app.current_user_id = <user_id>
    Tech Spec §2：所有受保护接口必须注入此变量。
    """
    await get_rls_db(db, str(current_user.id))

    return make_ok(
        UserProfileOut(
            id=str(current_user.id),
            role=current_user.role,
            nickname=current_user.nickname,
            avatar_url=current_user.avatar_url,
            is_active=current_user.is_active,
        )
    )
