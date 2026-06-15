from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user, get_current_user_allow_banned
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.users import UserMeOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/ban-status", response_model=None)
async def ban_status(
    current_user: Annotated[User, Depends(get_current_user_allow_banned)],
):
    """被封禁用户可见的封禁说明（§5.3.1）。普通用户返回 banned=false。"""
    return make_ok({
        "banned": not current_user.is_active,
        "ban_type": (None if current_user.is_active else
                     ("permanent" if current_user.banned_until is None else "temporary")),
        "reason": current_user.ban_reason,
        "banned_until": current_user.banned_until.isoformat() if current_user.banned_until else None,
    })


@router.post("/me/ban-appeal", response_model=None)
async def submit_ban_appeal(
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_allow_banned)],
):
    """被封禁用户提交封禁申诉（§5.3.1）。body={reason, evidence_urls?}。"""
    from app.services import ban_appeal_service
    rec = await ban_appeal_service.submit(
        db, user=current_user, reason=(body or {}).get("reason", ""),
        evidence_urls=(body or {}).get("evidence_urls"))
    await db.commit()
    return make_ok({"id": str(rec.id), "status": rec.status})


@router.get("/me/ban-appeals", response_model=None)
async def my_ban_appeals(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_allow_banned)],
):
    from app.services import ban_appeal_service
    return make_ok(await ban_appeal_service.list_mine(db, user_id=current_user.id))


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
            preferred_grade=current_user.preferred_grade,
            profile_completed=current_user.profile_completed,
            birth_year=current_user.birth_year,
            deactivation_scheduled_at=current_user.deactivation_scheduled_at,
            days_until_cancellation=days_until_cancellation,
        )
    )
