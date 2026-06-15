"""封禁申诉（§5.3.1）：被封用户提交 → 后台审核；通过则解封并补偿会员时长。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import BanAppeal, User


def _item(a: BanAppeal, *, nickname=None, phone=None, ban_reason=None) -> dict:
    return {
        "id": str(a.id), "user_id": str(a.user_id),
        "reason": a.reason, "evidence_urls": a.evidence_urls or [],
        "status": a.status, "note": a.note,
        "nickname": nickname, "phone": phone, "ban_reason": ban_reason,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
    }


async def submit(db: AsyncSession, *, user: User, reason: str,
                 evidence_urls: list[str] | None) -> BanAppeal:
    """被封用户提交申诉。"""
    if user.is_active:
        raise AppError(code=400, message="账号未被封禁，无需申诉")
    if not (reason or "").strip():
        raise AppError(code=400, message="请填写申诉说明")
    pending = await db.scalar(select(BanAppeal).where(and_(
        BanAppeal.user_id == user.id, BanAppeal.status == "pending")))
    if pending is not None:
        raise AppError(code=400, message="已有待审申诉，请耐心等待处理")
    rec = BanAppeal(id=uuid.uuid4(), user_id=user.id, reason=reason.strip(),
                    evidence_urls=evidence_urls or None, status="pending")
    db.add(rec)
    await db.flush()
    return rec


async def list_mine(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(BanAppeal).where(BanAppeal.user_id == user_id)
        .order_by(BanAppeal.created_at.desc()))).scalars().all()
    return [_item(a) for a in rows]


async def admin_list(db: AsyncSession, *, status: str = "pending",
                     skip: int = 0, limit: int = 50) -> dict:
    stmt = select(BanAppeal, User).join(User, BanAppeal.user_id == User.id)
    if status and status != "all":
        stmt = stmt.where(BanAppeal.status == status)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(BanAppeal.created_at.desc()).offset(skip).limit(limit))).all()
    return {"total": total, "items": [
        _item(a, nickname=u.nickname, phone=u.phone, ban_reason=u.ban_reason) for a, u in rows]}


async def review(db: AsyncSession, *, appeal_id: uuid.UUID, admin_id: uuid.UUID,
                 approve: bool, note: str | None) -> BanAppeal:
    """审核申诉。通过→解封(自动顺延会员=补偿封禁时长)；驳回→维持封禁。"""
    a = await db.get(BanAppeal, appeal_id)
    if a is None:
        raise AppError(code=404, message="申诉不存在")
    if a.status != "pending":
        raise AppError(code=400, message="该申诉已处理")
    a.status = "approved" if approve else "rejected"
    a.note = (note or "").strip() or None
    a.reviewed_by = admin_id
    a.reviewed_at = dt.datetime.now(dt.timezone.utc)
    if approve:
        from app.services import user_admin_service
        await user_admin_service.unban_user(db, user_id=a.user_id)  # 解封+顺延会员
    await db.flush()
    return a
