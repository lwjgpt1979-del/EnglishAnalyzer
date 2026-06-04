"""运营管理员账号密码认证（M5 / D-098）。

管理员 = role=platform_admin 的 users 行；不走微信，openid 用合成占位
"admin:{username}" 满足 NOT NULL/unique 约束。密码 bcrypt 落库。
"""
from __future__ import annotations

import uuid

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


async def create_admin(db: AsyncSession, *, username: str, password: str) -> User:
    """创建 / 重置一个 platform_admin 账号。

    - username 已存在 → 视为重置密码（不新建行）。
    - 不存在 → 新建，openid 合成 "admin:{username}"，role=platform_admin。
    仅设置 NOT NULL 必需列（openid/role）+ username/password_hash；其余列
    （is_active/created_at/profile_completed/is_anonymized/updated_at）均有
    server_default，合规字段均 nullable。
    """
    existing = (await db.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if existing is not None:
        existing.password_hash = hash_password(password)
        existing.role = "platform_admin"
        return existing
    user = User(
        id=uuid.uuid4(),
        openid=f"admin:{username}",
        username=username,
        password_hash=hash_password(password),
        role="platform_admin",
    )
    db.add(user)
    return user


async def authenticate(
    db: AsyncSession, *, username: str, password: str,
) -> User | None:
    """校验用户名+密码，成功返回 platform_admin 用户，否则 None。"""
    user = (await db.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if user is None or not user.password_hash:
        return None
    if str(user.role) not in ("platform_admin", "institution_admin"):
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_institution_admin(
    db: AsyncSession, *, username: str, password: str, institution_id: uuid.UUID,
) -> User:
    """创建 / 重置一个 institution_admin 账号，绑定到指定机构。

    - username 已存在 → 重置密码 + 角色 + 机构（不新建行）。
    - 不存在 → 新建，openid 合成 "inst:{username}"，role=institution_admin。
    """
    existing = (await db.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if existing is not None:
        existing.password_hash = hash_password(password)
        existing.role = "institution_admin"
        existing.institution_id = institution_id
        return existing
    user = User(
        id=uuid.uuid4(),
        openid=f"inst:{username}",
        username=username,
        password_hash=hash_password(password),
        role="institution_admin",
        institution_id=institution_id,
    )
    db.add(user)
    return user
