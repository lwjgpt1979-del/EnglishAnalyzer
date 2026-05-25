import uuid

from fastapi import APIRouter, Depends
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

import app.services.auth_service as auth_service
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.d1_users import User
from app.schemas.auth import RefreshRequest, TokenResponse, WxLoginRequest
from app.schemas.base import BaseResponse, make_ok

router = APIRouter(prefix="/auth", tags=["auth"])


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
