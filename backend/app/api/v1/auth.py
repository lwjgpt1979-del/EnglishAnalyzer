import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.auth_service as auth_service
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, decode_token, get_current_user
from app.models.d1_users import User
from app.schemas.auth import RefreshRequest, TokenResponse, WxLoginRequest
from app.schemas.base import BaseResponse, make_ok
from app.schemas.compliance import (
    CompleteProfileRequest,
    CompleteProfileResponse,
    GuardianVerifyRequest,
    CancelAccountConfirm,
    CancellationStatusOut,
)
from app.services.auth_service import complete_profile, guardian_verify
from app.services.cancellation_service import (
    request_cancellation,
    confirm_cancellation,
    revoke_cancellation,
    status_for,
)

router = APIRouter(prefix="/auth", tags=["auth"])

UserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/wx-login", response_model=BaseResponse[TokenResponse])
async def wx_login(
    body: WxLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """微信小程序登录。

    前端调用 wx.login() 获取 code → 发送到此接口。
    后端用 code 换取 openid，upsert 用户，返回 JWT 双 token。
    session_key 不落库，不透传前端（Tech Spec §1.2）。
    """
    wx_data = await auth_service.wechat_code2session(body.code)
    user = await auth_service.upsert_user(db, openid=wx_data["openid"])
    await db.commit()

    return make_ok(
        TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id)),
        )
    )


@router.post("/refresh", response_model=BaseResponse[TokenResponse])
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用 refresh_token 换取新 access_token。

    refresh_token 过期或类型错误时返回 401。
    """
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except JWTError:
        raise AppError(code=401, message="refresh_token 无效或已过期，请重新登录")

    user_id = payload.get("sub", "")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppError(code=401, message="用户不存在或已被封禁")

    return make_ok(
        TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id)),
        )
    )


@router.post("/complete-profile", response_model=BaseResponse[CompleteProfileResponse])
async def complete_profile_api(body: CompleteProfileRequest, db: DbDep, current_user: UserDep):
    """完善用户档案（年龄 + 协议 + 手机号）。"""
    res = await complete_profile(
        db, user=current_user,
        birth_year=body.birth_year,
        guardian_phone=body.guardian_phone,
        user_phone=body.user_phone,
        agreement_version=body.agreement_version,
        preferred_textbook_version=body.preferred_textbook_version,
        preferred_grade=body.preferred_grade,
        preferred_semester=body.preferred_semester,
    )
    await db.commit()
    return make_ok(res)


@router.post("/guardian-verify", response_model=BaseResponse[dict])
async def guardian_verify_api(body: GuardianVerifyRequest, db: DbDep, current_user: UserDep):
    """验证监护人手机验证码，完成未成年人档案。"""
    await guardian_verify(db, user=current_user, code=body.code)
    await db.commit()
    return make_ok({"profile_completed": True})


@router.post("/cancel-account/request", response_model=BaseResponse[dict])
async def cancel_request_api(db: DbDep, current_user: UserDep):
    """申请注销账号（发送短信验证码）。"""
    await request_cancellation(db, user=current_user)
    await db.commit()
    return make_ok({"sent": True})


@router.post("/cancel-account/confirm", response_model=BaseResponse[CancellationStatusOut])
async def cancel_confirm_api(body: CancelAccountConfirm, db: DbDep, current_user: UserDep):
    """确认注销（验证码核对），进入 15 天冷静期。"""
    await confirm_cancellation(db, user=current_user, code=body.code)
    await db.commit()
    return make_ok(status_for(current_user))


@router.post("/cancel-account/revoke", response_model=BaseResponse[dict])
async def cancel_revoke_api(db: DbDep, current_user: UserDep):
    """撤销注销申请（冷静期内有效）。"""
    await revoke_cancellation(db, user=current_user)
    await db.commit()
    return make_ok({"revoked": True})
