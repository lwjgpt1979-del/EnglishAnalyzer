"""优惠券 / 兑换码（SP-4）。

后台发券（直发指定用户 / 兑换码批量）→ 用户领取 → 下单抵扣。
抵扣类型：
  amount  : discount_value = 抵扣分，满 min_amount_fen 可用，封顶=订单金额。
  percent : discount_value = 折扣率万分比（9000=9折，付 90%），discount=金额×(10000-value)/10000，
            可由 max_discount_fen 封顶。
所有真实扣款仍走支付通道；本模块只管券的发放/校验/核销。
"""
from __future__ import annotations

import datetime as dt
import random
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import Coupon, CouponGrant

_DISCOUNT_TYPES = {"amount", "percent"}
_SCOPES = {"all", "semester", "addon", "renew", "upgrade", "new"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d):
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _gen_code(n: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _coupon_item(c: Coupon) -> dict:
    return {
        "id": str(c.id), "name": c.name, "discount_type": c.discount_type,
        "discount_value": c.discount_value, "min_amount_fen": c.min_amount_fen,
        "max_discount_fen": c.max_discount_fen, "scope": c.scope,
        "redeem_code": c.redeem_code, "redeem_quota": c.redeem_quota,
        "redeemed_count": c.redeemed_count, "per_user_limit": c.per_user_limit,
        "valid_from": c.valid_from.isoformat() if c.valid_from else None,
        "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _desc(c: Coupon) -> str:
    if c.discount_type == "amount":
        s = f"满{c.min_amount_fen // 100}元减{c.discount_value / 100:g}元" if c.min_amount_fen \
            else f"减{c.discount_value / 100:g}元"
    else:
        zhe = (10000 - c.discount_value) / 1000  # 9000→1.0? no
        s = f"{c.discount_value / 1000:g}折"
        if c.min_amount_fen:
            s = f"满{c.min_amount_fen // 100}元{s}"
        if c.max_discount_fen:
            s += f"（最高减{c.max_discount_fen / 100:g}元）"
    return s


def compute_discount(c: Coupon, amount_fen: int) -> int:
    """给定券模板与订单金额，返回可抵扣分（不校验有效期/归属）。"""
    if amount_fen < (c.min_amount_fen or 0):
        return 0
    if c.discount_type == "amount":
        d = min(c.discount_value, amount_fen)
    else:
        d = amount_fen * (10000 - c.discount_value) // 10000
        if c.max_discount_fen:
            d = min(d, c.max_discount_fen)
    return max(0, min(d, amount_fen))


def _validate_usable(c: Coupon, *, scope: str, amount_fen: int) -> int:
    now = _now()
    if not c.is_active:
        raise AppError(code=400, message="优惠券不可用")
    if c.valid_from and now < _aware(c.valid_from):
        raise AppError(code=400, message="优惠券未到生效时间")
    if c.valid_until and now > _aware(c.valid_until):
        raise AppError(code=400, message="优惠券已过期")
    if c.scope != "all" and scope != c.scope:
        raise AppError(code=400, message="该优惠券不适用于本订单类型")
    if amount_fen < (c.min_amount_fen or 0):
        raise AppError(code=400, message=f"订单需满 {c.min_amount_fen / 100:g} 元方可使用")
    d = compute_discount(c, amount_fen)
    if d <= 0:
        raise AppError(code=400, message="该券对本订单无抵扣")
    return d


# ── 管理：建券 / 发券 ────────────────────────────────────────────────────────
async def admin_create(db: AsyncSession, *, admin_id: uuid.UUID, name: str,
                       discount_type: str, discount_value: int,
                       min_amount_fen: int = 0, max_discount_fen: int | None = None,
                       scope: str = "all", per_user_limit: int = 1,
                       valid_days: int | None = None,
                       with_redeem_code: bool = False, redeem_quota: int | None = None) -> Coupon:
    if discount_type not in _DISCOUNT_TYPES:
        raise AppError(code=400, message="无效抵扣类型")
    if scope not in _SCOPES:
        raise AppError(code=400, message="无效适用范围")
    if discount_value <= 0:
        raise AppError(code=400, message="抵扣值需大于 0")
    if discount_type == "percent" and discount_value >= 10000:
        raise AppError(code=400, message="折扣率需小于 10000（即不足原价）")
    code = None
    if with_redeem_code:
        for _ in range(8):
            cand = _gen_code(10)
            exists = await db.scalar(select(Coupon.id).where(Coupon.redeem_code == cand))
            if not exists:
                code = cand
                break
        if code is None:
            raise AppError(code=500, message="兑换码生成失败，请重试")
    valid_until = _now() + dt.timedelta(days=valid_days) if valid_days else None
    c = Coupon(
        id=uuid.uuid4(), name=name.strip()[:100], discount_type=discount_type,
        discount_value=int(discount_value), min_amount_fen=int(min_amount_fen or 0),
        max_discount_fen=(int(max_discount_fen) if max_discount_fen else None),
        scope=scope, redeem_code=code, redeem_quota=redeem_quota,
        per_user_limit=int(per_user_limit or 1), valid_until=valid_until,
        is_active=True, created_by=admin_id)
    db.add(c)
    await db.flush()
    return c


async def admin_list(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    stmt = select(Coupon).order_by(Coupon.created_at.desc())
    total = int(await db.scalar(select(func.count()).select_from(Coupon)) or 0)
    rows = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    items = []
    for c in rows:
        granted = int(await db.scalar(
            select(func.count()).select_from(CouponGrant).where(
                CouponGrant.coupon_id == c.id)) or 0)
        used = int(await db.scalar(
            select(func.count()).select_from(CouponGrant).where(
                CouponGrant.coupon_id == c.id, CouponGrant.status == "used")) or 0)
        d = _coupon_item(c)
        d.update({"granted": granted, "used": used, "desc": _desc(c)})
        items.append(d)
    return {"total": total, "items": items}


async def admin_set_active(db: AsyncSession, *, coupon_id: uuid.UUID, is_active: bool) -> Coupon:
    c = await db.get(Coupon, coupon_id)
    if c is None:
        raise AppError(code=404, message="优惠券不存在")
    c.is_active = is_active
    await db.flush()
    return c


async def admin_grant(db: AsyncSession, *, coupon_id: uuid.UUID,
                      user_ids: list[uuid.UUID]) -> int:
    """直接发券给指定用户（去重，已持有未使用则跳过）。返回新增张数。"""
    c = await db.get(Coupon, coupon_id)
    if c is None:
        raise AppError(code=404, message="优惠券不存在")
    n = 0
    for uid in user_ids:
        held = int(await db.scalar(
            select(func.count()).select_from(CouponGrant).where(
                CouponGrant.coupon_id == coupon_id, CouponGrant.user_id == uid)) or 0)
        if held >= (c.per_user_limit or 1):
            continue
        db.add(CouponGrant(id=uuid.uuid4(), coupon_id=coupon_id, user_id=uid, status="unused"))
        n += 1
    await db.flush()
    return n


# ── 用户：兑换 / 我的券 ──────────────────────────────────────────────────────
async def redeem(db: AsyncSession, *, user_id: uuid.UUID, code: str) -> dict:
    code = (code or "").strip().upper()
    if not code:
        raise AppError(code=400, message="请输入兑换码")
    c = (await db.execute(select(Coupon).where(Coupon.redeem_code == code))).scalar_one_or_none()
    if c is None:
        raise AppError(code=404, message="兑换码无效")
    if not c.is_active:
        raise AppError(code=400, message="该兑换码已停用")
    if c.valid_until and _now() > _aware(c.valid_until):
        raise AppError(code=400, message="该兑换码已过期")
    if c.redeem_quota is not None and (c.redeemed_count or 0) >= c.redeem_quota:
        raise AppError(code=400, message="兑换码已被领完")
    held = int(await db.scalar(
        select(func.count()).select_from(CouponGrant).where(
            CouponGrant.coupon_id == c.id, CouponGrant.user_id == user_id)) or 0)
    if held >= (c.per_user_limit or 1):
        raise AppError(code=400, message="您已领取过该优惠券")
    db.add(CouponGrant(id=uuid.uuid4(), coupon_id=c.id, user_id=user_id, status="unused"))
    c.redeemed_count = (c.redeemed_count or 0) + 1
    await db.flush()
    return {"coupon": _coupon_item(c), "desc": _desc(c)}


async def list_mine(db: AsyncSession, *, user_id: uuid.UUID,
                    status: str = "unused") -> dict:
    stmt = (select(CouponGrant, Coupon)
            .join(Coupon, Coupon.id == CouponGrant.coupon_id)
            .where(CouponGrant.user_id == user_id))
    if status and status != "all":
        stmt = stmt.where(CouponGrant.status == status)
    rows = (await db.execute(stmt.order_by(CouponGrant.created_at.desc()))).all()
    now = _now()
    items = []
    for g, c in rows:
        expired = bool(c.valid_until and now > _aware(c.valid_until))
        items.append({
            "grant_id": str(g.id), "coupon_id": str(c.id), "name": c.name,
            "desc": _desc(c), "scope": c.scope, "status": g.status,
            "min_amount_fen": c.min_amount_fen, "expired": expired,
            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        })
    return {"items": items}


async def list_applicable(db: AsyncSession, *, user_id: uuid.UUID,
                          amount_fen: int, scope: str) -> dict:
    """下单页：返回对本订单可用的券及抵扣额（已按抵扣额降序）。"""
    rows = (await db.execute(
        select(CouponGrant, Coupon).join(Coupon, Coupon.id == CouponGrant.coupon_id)
        .where(CouponGrant.user_id == user_id, CouponGrant.status == "unused"))).all()
    out = []
    for g, c in rows:
        try:
            d = _validate_usable(c, scope=scope, amount_fen=amount_fen)
        except AppError:
            continue
        out.append({"grant_id": str(g.id), "coupon_id": str(c.id), "name": c.name,
                    "desc": _desc(c), "discount_fen": d})
    out.sort(key=lambda x: x["discount_fen"], reverse=True)
    return {"items": out}


# ── 下单抵扣（由 order 流程调用）─────────────────────────────────────────────
async def apply_to_order(db: AsyncSession, *, grant_id: uuid.UUID, user_id: uuid.UUID,
                         order, scope: str) -> int:
    """校验并把券用在订单上：扣减 order.amount_fen，标记 grant used。返回抵扣分。
    调用方负责 commit。"""
    g = await db.get(CouponGrant, grant_id)
    if g is None or g.user_id != user_id:
        raise AppError(code=404, message="优惠券不存在")
    if g.status != "unused":
        raise AppError(code=400, message="该优惠券已使用")
    c = await db.get(Coupon, g.coupon_id)
    if c is None:
        raise AppError(code=404, message="优惠券不存在")
    d = _validate_usable(c, scope=scope, amount_fen=order.amount_fen)
    order.discount_fen = d
    order.amount_fen = max(0, order.amount_fen - d)
    order.coupon_grant_id = g.id
    g.status = "used"
    g.order_id = order.id
    g.used_at = _now()
    await db.flush()
    return d


async def release_on_cancel(db: AsyncSession, *, order_id: uuid.UUID) -> None:
    """订单取消/退款时把券退还为 unused（如业务需要）。"""
    g = (await db.execute(
        select(CouponGrant).where(CouponGrant.order_id == order_id,
                                  CouponGrant.status == "used"))).scalar_one_or_none()
    if g is not None:
        g.status = "unused"
        g.order_id = None
        g.used_at = None
        await db.flush()
