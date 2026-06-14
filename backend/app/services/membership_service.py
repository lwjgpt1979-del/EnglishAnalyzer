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
) -> "Membership | None":
    """V1（旧 Membership）和 V2（PurchasedSemester）双模式。调用方负责 commit。

    - V2：order.semester_count 非空 → 创建 PurchasedSemester，返回 None
    - V1 new / upgrade：停用旧记录 → 创建新记录
    - V1 renew：在原记录上延长 expires_at
    """
    # 加量包分支：发放该功能加量次数，不创建会员
    if getattr(order, "addon_feature_key", None):
        from app.services import entitlement_service
        acfg = await entitlement_service.addon_config(db, order.addon_feature_key)
        await entitlement_service.grant_addon(
            db, user_id=order.beneficiary_id, key=order.addon_feature_key, n=acfg["pack_size"])
        from app.services.notification_service import emit_membership
        try:
            await emit_membership(
                db, user_id=order.beneficiary_id, title="加量包购买成功",
                content=f"已到账 {acfg['pack_size']} 次，配额用完后自动使用。", order_id=order.id)
        except Exception:
            pass
        return None

    # V2 分支
    if order.semester_count and order.purchased_semester_ids:
        from app.services.semester_service import create_purchased_semesters
        await create_purchased_semesters(
            db, user_id=order.beneficiary_id, tier=str(order.tier),
            semesters=order.purchased_semester_ids,
            order_id=order.id,
        )
        # 通知
        from app.services.notification_service import emit_membership
        try:
            await emit_membership(
                db, user_id=order.beneficiary_id,
                title="学期会员开通成功",
                content=f"已开通 {order.semester_count} 个学期，6 个月有效。",
                order_id=order.id,
            )
        except Exception:
            pass
        return None  # V2 不返回 Membership 对象（兼容调用方对 None 不报错）

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
        # —— 发"会员开通成功"通知（D-074 Module 7B）——
        from app.services.notification_service import emit_membership
        try:
            await emit_membership(
                db, user_id=user_id,
                title="会员续费成功",
                content=f"您的{existing.tier}会员已续费，到期 {existing.expires_at.strftime('%Y-%m-%d')}。",
                order_id=order.id,
            )
        except Exception:
            pass
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
    # —— 发"会员开通成功"通知（D-074 Module 7B）——
    from app.services.notification_service import emit_membership
    try:
        await emit_membership(
            db, user_id=user_id,
            title="会员开通成功",
            content=f"您的{membership.tier}会员已激活，到期 {membership.expires_at.strftime('%Y-%m-%d')}。",
            order_id=order.id,
        )
    except Exception:
        pass
    return membership
