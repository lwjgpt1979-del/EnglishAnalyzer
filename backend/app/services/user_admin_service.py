"""平台超管：C 端用户搜索 + 封禁/解封（§5.3.1）。

is_active=False 即封禁；banned_until 空=永久，有值=临时（到期鉴权时自动解封）。
退款引擎已识别 REJECT_BANNED；鉴权层 is_active=False 直接 401/403。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User


def _to_item(u: User) -> dict:
    return {
        "id": str(u.id),
        "nickname": u.nickname,
        "phone": u.phone,
        "role": str(u.role),
        "is_active": u.is_active,
        "banned": not u.is_active,
        "ban_reason": u.ban_reason,
        "banned_until": u.banned_until.isoformat() if u.banned_until else None,
        "ban_type": (None if u.is_active else ("permanent" if u.banned_until is None else "temporary")),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def list_users(db: AsyncSession, *, q: str = "", skip: int = 0,
                     limit: int = 50) -> dict:
    """按昵称/手机号/ID 搜索 C 端用户（学生/教师/家长）。"""
    stmt = select(User).where(User.role.in_(("student", "teacher", "relative")))
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        conds = [User.nickname.ilike(like), User.phone.ilike(like)]
        try:
            conds.append(User.id == uuid.UUID(q))
        except ValueError:
            pass
        stmt = stmt.where(or_(*conds))
    total = len(((await db.execute(stmt)).scalars()).all())
    rows = (await db.execute(
        stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return {"total": total, "items": [_to_item(u) for u in rows]}


async def ban_user(db: AsyncSession, *, user_id: uuid.UUID, reason: str,
                   days: int | None) -> User:
    """封禁。days=None → 永久；days>0 → 临时（到期自动解封）。"""
    if not (reason or "").strip():
        raise AppError(code=400, message="封禁原因必填")
    u = await db.get(User, user_id)
    if u is None:
        raise AppError(code=404, message="用户不存在")
    if u.role == "platform_admin":
        raise AppError(code=400, message="不能封禁管理员账号")
    now = dt.datetime.now(dt.timezone.utc)
    u.is_active = False
    u.ban_reason = reason.strip()
    u.banned_at = now
    u.banned_until = (now + dt.timedelta(days=days)) if days else None
    await db.flush()
    return u


def _aware(ts):
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


async def resume_membership_after_ban(db: AsyncSession, user: User) -> None:
    """解封时把会员有效期顺延封禁时长（封禁期暂停计时，不浪费剩余会员，§5.3.1）。"""
    banned_at = _aware(user.banned_at)
    if banned_at is None:
        return
    from app.models.d2_payments import Membership
    paused = dt.datetime.now(dt.timezone.utc) - banned_at
    if paused.total_seconds() <= 0:
        return
    mem = await db.scalar(select(Membership).where(and_(
        Membership.user_id == user.id, Membership.is_active.is_(True))))
    if mem is not None and mem.expires_at is not None:
        mem.expires_at = _aware(mem.expires_at) + paused


async def unban_user(db: AsyncSession, *, user_id: uuid.UUID) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise AppError(code=404, message="用户不存在")
    await resume_membership_after_ban(db, u)   # 先顺延会员，再清封禁态
    u.is_active = True
    u.ban_reason = None
    u.banned_until = None
    u.banned_at = None
    await db.flush()
    return u


async def auto_ban(db: AsyncSession, *, user_id: uuid.UUID, reason: str, days: int = 7) -> None:
    """系统自动封禁（如内容审核命中）。供审核流水线调用，默认临时 7 天。"""
    u = await db.get(User, user_id)
    if u is None or u.role == "platform_admin" or not u.is_active:
        return
    now = dt.datetime.now(dt.timezone.utc)
    u.is_active = False
    u.ban_reason = f"[系统]{reason}"
    u.banned_at = now
    u.banned_until = now + dt.timedelta(days=days)
    await db.flush()
