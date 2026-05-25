import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User


async def wechat_code2session(code: str) -> dict:
    """调用微信 jscode2session 接口，返回 {openid, session_key}。

    文档: https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
    session_key 不落库，不透传业务层（Tech Spec §1.2）。
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.wechat_code2session_url,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()

    if data.get("errcode") and data["errcode"] != 0:
        raise AppError(
            code=401,
            message=f"微信登录失败（{data.get('errmsg', 'unknown')}），请重试",
        )

    openid = data.get("openid")
    if not openid:
        raise AppError(code=401, message="微信未返回 openid，请重试")

    return {"openid": openid, "session_key": data.get("session_key", "")}


async def upsert_user(db: AsyncSession, *, openid: str) -> User:
    """按 openid 查找用户；不存在则创建（默认 role=student）。

    使用 db.flush() 而非 db.commit()，让调用方控制事务边界。
    """
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            openid=openid,
            role="student",
            is_active=True,
        )
        db.add(user)
        await db.flush()  # get id without committing

    return user
