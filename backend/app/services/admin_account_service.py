"""管理员账号管理(RBAC):子管理员建号/改模块权限/停用/重置密码。

- admin_modules=NULL → 全权超管;非空数组 → 仅可访问所列模块(单点强制见 admin.py AdminDep)。
- 账号管理本身仅超管可操作(端点里校验),防止子管理员自我提权。
- 密码复用 admin_auth_service(bcrypt);停用走 users.is_active(get_current_user 全局拦截)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.module_map import MODULES
from app.models.d1_users import User
from app.services import admin_auth_service as auth


def _clean_modules(modules: list[str] | None) -> list[str] | None:
    """None=全权;[] 视为配置错误(什么都看不了没意义)→ 报错让运营重选。"""
    if modules is None:
        return None
    mods = [m for m in modules if m in MODULES]
    if not mods:
        raise AppError(code=400, message="至少勾选一个模块(或选「全权」)")
    return mods


def _row(u: User) -> dict:
    return {"id": str(u.id), "username": u.username, "nickname": u.nickname,
            "modules": u.admin_modules, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None}


async def list_admins(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    conds = [User.role == "platform_admin", User.username.is_not(None)]
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(User).where(*conds))).scalar() or 0
    rows = (await db.execute(
        sa.select(User).where(*conds).order_by(User.created_at)
        .offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_row(u) for u in rows]}


async def create(db: AsyncSession, *, username: str, password: str,
                 nickname: str | None, modules: list[str] | None) -> dict:
    username = (username or "").strip()
    if not username or len(password or "") < 8:
        raise AppError(code=400, message="用户名必填,密码至少 8 位")
    exists = (await db.execute(
        sa.select(User.id).where(User.username == username))).scalar_one_or_none()
    if exists is not None:
        raise AppError(code=400, message=f"用户名 {username} 已存在")
    u = await auth.create_admin(db, username=username, password=password)
    u.nickname = (nickname or "").strip() or None
    u.admin_modules = _clean_modules(modules)
    await db.flush()
    return _row(u)


async def _get_admin(db: AsyncSession, admin_id: uuid.UUID) -> User:
    u = (await db.execute(sa.select(User).where(
        User.id == admin_id, User.role == "platform_admin"))).scalar_one_or_none()
    if u is None:
        raise AppError(code=404, message="管理员不存在")
    return u


async def update(db: AsyncSession, admin_id: uuid.UUID, *, operator: User,
                 nickname: str | None = None, modules: list[str] | None = ...,
                 is_active: bool | None = None) -> dict:
    """modules 传 None=改为全权,不传(...)=不动;is_active=False 停用(立即失效)。"""
    u = await _get_admin(db, admin_id)
    if u.id == operator.id and is_active is False:
        raise AppError(code=400, message="不能停用自己")
    if u.id == operator.id and modules is not ... and modules is not None:
        raise AppError(code=400, message="不能给自己降权(防误锁),请让其他超管操作")
    if nickname is not None:
        u.nickname = nickname.strip() or None
    if modules is not ...:
        u.admin_modules = _clean_modules(modules)
    if is_active is not None:
        u.is_active = is_active
    await db.flush()
    return _row(u)


async def reset_password(db: AsyncSession, admin_id: uuid.UUID, *, password: str) -> dict:
    if len(password or "") < 8:
        raise AppError(code=400, message="密码至少 8 位")
    u = await _get_admin(db, admin_id)
    u.password_hash = auth.hash_password(password)
    await db.flush()
    return {"id": str(u.id)}
