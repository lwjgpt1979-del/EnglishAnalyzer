"""会员 CRUD 业务逻辑。

规则：
- 每个用户同时只有一条 is_active=true 的 Membership（DB 部分唯一索引保证）。
- new / upgrade：停用旧记录（若有），创建新记录。
- renew：延长当前记录的 expires_at。
- 月份计算使用 _add_months() 避免引入 dateutil 依赖。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d2_payments import Membership, Order


def _add_months(dt: datetime, months: int) -> datetime:
    """将 datetime 加 months 个月，处理月末溢出（如 1月31日+1月→2月28日）。"""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
    ]
    day = min(dt.day, days_in_month[month - 1])
    return dt.replace(year=year, month=month, day=day)


async def get_active_membership(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> Membership | None:
    """返回当前激活的会员记录，无则返回 None。"""
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def activate_membership(
    db: AsyncSession,
    *,
    order: Order,
) -> Membership:
    """根据订单类型激活/续费/升级会员。调用方负责 commit。

    - new / upgrade：停用旧记录 → 创建新记录
    - renew：在原记录上延长 expires_at
    """
    user_id = order.beneficiary_id
    existing = await get_active_membership(db, user_id=user_id)
    now = datetime.now(timezone.utc)

    if order.order_type == "renew" and existing and existing.tier == order.tier:
        # 续费：从当前到期时间（或现在）延长
        base = (
            existing.expires_at
            if existing.expires_at and existing.expires_at > now
            else now
        )
        existing.expires_at = _add_months(base, order.duration_months)
        await db.flush()
        return existing

    # new 或 upgrade：停用旧记录
    if existing is not None:
        existing.is_active = False
        await db.flush()

    # 创建新会员记录
    membership = Membership(
        id=uuid.uuid4(),
        user_id=user_id,
        order_id=order.id,
        tier=order.tier,
        started_at=now,
        expires_at=_add_months(now, order.duration_months),
        is_active=True,
    )
    db.add(membership)
    await db.flush()
    return membership
