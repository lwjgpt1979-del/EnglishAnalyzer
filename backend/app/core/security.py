import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.d1_users import User
from app.core.exceptions import AppError

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, role: str) -> str:
    """签发 access token，有效期 2 小时（Tech Spec §1.5）。"""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """签发 refresh token，有效期 30 天（Tech Spec §1.5）。"""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict:
    """解码并验证 JWT。type 不匹配时抛出 JWTError。"""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise JWTError(f"token type mismatch: expected {expected_type}")
    return payload


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """FastAPI 依赖：从 Authorization Bearer token 解析当前用户。

    未携带 token 或 token 无效 → 401。
    用户被封禁（is_active=False）→ 403。
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未授权，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except JWTError:
        raise unauthorized

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise unauthorized

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized

    # 注销懒触发：在 is_active 校验前执行（避免循环引用，函数内 import）
    if user.deactivation_scheduled_at is not None and not user.is_anonymized:
        from app.services.cancellation_service import execute_cancellation_if_due
        executed = await execute_cancellation_if_due(db, user=user)
        if executed:
            await db.commit()

    # 冷静期内（已申请注销但尚未执行）允许通过，以便 revoke/me 等端点正常工作
    if not user.is_active and not (
        user.deactivation_scheduled_at is not None
        and not user.is_anonymized
        and user.deactivation_scheduled_at > datetime.now(timezone.utc)
    ):
        raise AppError(code=401, message="用户不存在或已被封禁")

    return user


from typing import Callable, Awaitable


def require_role(*allowed_roles: str) -> Callable[..., Awaitable[User]]:
    """生成依赖：要求 current_user.role 在 allowed_roles 中，否则 403。"""
    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        if str(current_user.role) not in allowed_roles:
            raise AppError(code=403, message="权限不足")
        return current_user
    return _dep
