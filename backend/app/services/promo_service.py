"""限时活动价 campaign（§5.7）。

活动期内覆盖学期会员定价；到期自动恢复（按时间窗判定，无需 cron）。
仅作用于「学期会员」购买路径（V2 主产品，§5.7 价格矩阵）。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import Order, PromoCampaign

_LIMIT_TYPES = {"none", "once", "total"}
_TIER_COL = {"basic": "price_basic", "pro": "price_pro", "promax": "price_promax"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d):
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _item(c: PromoCampaign) -> dict:
    return {
        "id": str(c.id), "name": c.name,
        "price_basic": c.price_basic, "price_pro": c.price_pro, "price_promax": c.price_promax,
        "starts_at": c.starts_at.isoformat() if c.starts_at else None,
        "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        "limit_type": c.limit_type, "total_quota": c.total_quota, "sold_count": c.sold_count,
        "is_promotional": c.is_promotional, "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def campaign_tier_price(c: PromoCampaign, tier: str) -> int | None:
    """该活动对某档位的活动价（元/学期）；None=该档不参加。"""
    return getattr(c, _TIER_COL.get(tier, ""), None)


async def active_campaign(db: AsyncSession, *, now: dt.datetime | None = None) -> PromoCampaign | None:
    """当前生效活动（is_active 且在时间窗内）。多个则取最近开始的。"""
    now = now or _now()
    rows = (await db.execute(
        select(PromoCampaign).where(and_(
            PromoCampaign.is_active.is_(True),
            PromoCampaign.starts_at <= now,
            PromoCampaign.ends_at >= now))
        .order_by(PromoCampaign.starts_at.desc()))).scalars().all()
    return rows[0] if rows else None


async def effective_semester_pricing(db: AsyncSession) -> dict:
    """学期定价（叠加当前活动）：返回实售价 + 划线价(原价) + 活动信息。

    无活动时实售=原价、划线价取后台配置的 list_*；有活动时参加活动的档位
    实售=活动价、划线价=原价。
    """
    from app.services.pricing_service import get_semester_pricing
    base = await get_semester_pricing(db)
    out = {
        "basic": base.basic, "pro": base.pro, "promax": base.promax,
        "list_basic": base.list_basic or 0, "list_pro": base.list_pro or 0,
        "list_promax": base.list_promax or 0,
        "campaign": None,
    }
    c = await active_campaign(db)
    if c is None:
        return out
    for tier, base_price in (("basic", base.basic), ("pro", base.pro), ("promax", base.promax)):
        ap = campaign_tier_price(c, tier)
        if ap is not None and ap > 0:
            out[tier] = ap                       # 实售=活动价
            out[f"list_{tier}"] = base_price     # 划线价=原价
    out["campaign"] = {
        "id": str(c.id), "name": c.name,
        "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        "is_promotional": c.is_promotional,
    }
    return out


async def resolve_for_order(db: AsyncSession, *, tier: str, payer_id: uuid.UUID,
                            semester_count: int) -> tuple[PromoCampaign | None, int | None]:
    """下单时解析活动：返回 (campaign, 活动单价元/学期)。无适用活动→(None, None)。

    命中活动则校验限购规则；total 限量在此处预占（调用方 record_sale 落实）。
    """
    c = await active_campaign(db)
    if c is None:
        return None, None
    ap = campaign_tier_price(c, tier)
    if ap is None or ap <= 0:
        return None, None   # 该档位不参加活动 → 走原价
    # 限购校验
    if c.limit_type == "once":
        prior = int(await db.scalar(
            select(func.count()).select_from(Order).where(and_(
                Order.promo_campaign_id == c.id,
                Order.payer_id == payer_id,
                Order.status.in_(("paid", "refunded", "partial_refunded", "pending"))))) or 0)
        if prior > 0:
            raise AppError(code=400, message="该活动每人限购 1 次")
    elif c.limit_type == "total" and c.total_quota is not None:
        if (c.sold_count or 0) >= c.total_quota:
            raise AppError(code=400, message="活动名额已抢完")
    return c, ap


async def record_sale(db: AsyncSession, *, campaign: PromoCampaign) -> None:
    """活动成单：sold_count +1（每笔订单计 1）。"""
    campaign.sold_count = (campaign.sold_count or 0) + 1
    await db.flush()


# ── admin CRUD ───────────────────────────────────────────────────────────────
async def admin_list(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    total = int(await db.scalar(select(func.count()).select_from(PromoCampaign)) or 0)
    rows = (await db.execute(
        select(PromoCampaign).order_by(PromoCampaign.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    now = _now()
    items = []
    for c in rows:
        d = _item(c)
        d["status"] = ("stopped" if not c.is_active
                       else "upcoming" if _aware(c.starts_at) > now
                       else "ended" if _aware(c.ends_at) < now
                       else "live")
        items.append(d)
    return {"total": total, "items": items}


async def admin_create(db: AsyncSession, *, admin_id: uuid.UUID, name: str,
                       starts_at: dt.datetime, ends_at: dt.datetime,
                       price_basic: int | None = None, price_pro: int | None = None,
                       price_promax: int | None = None, limit_type: str = "none",
                       total_quota: int | None = None, is_promotional: bool = True) -> PromoCampaign:
    if not (name or "").strip():
        raise AppError(code=400, message="活动名称不能为空")
    if limit_type not in _LIMIT_TYPES:
        raise AppError(code=400, message="无效限购类型")
    if _aware(ends_at) <= _aware(starts_at):
        raise AppError(code=400, message="结束时间须晚于开始时间")
    if not any(p and p > 0 for p in (price_basic, price_pro, price_promax)):
        raise AppError(code=400, message="至少为一个档位设置活动价")
    if limit_type == "total" and not (total_quota and total_quota > 0):
        raise AppError(code=400, message="总限量活动需设置名额数")
    c = PromoCampaign(
        id=uuid.uuid4(), name=name.strip()[:100],
        price_basic=price_basic or None, price_pro=price_pro or None,
        price_promax=price_promax or None, starts_at=starts_at, ends_at=ends_at,
        limit_type=limit_type, total_quota=(total_quota if limit_type == "total" else None),
        is_promotional=is_promotional, is_active=True, created_by=admin_id)
    db.add(c)
    await db.flush()
    return c


async def admin_set_active(db: AsyncSession, *, campaign_id: uuid.UUID, is_active: bool) -> PromoCampaign:
    c = await db.get(PromoCampaign, campaign_id)
    if c is None:
        raise AppError(code=404, message="活动不存在")
    c.is_active = is_active
    await db.flush()
    return c
