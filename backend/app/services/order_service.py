"""订单 CRUD 业务逻辑。

价格表（分）：
  tier     1 月    3 月    12 月
  basic    2900    7900   28800
  pro      4900   13800   49800
  promax   9900   28800   98800
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import Order

# ── 价格表（硬编码；后台可配置化留待后续迭代）────────────────────────────────

PRICE_TABLE: dict[str, dict[int, int]] = {
    "basic":  {1: 2900,  3: 7900,  12: 28800},
    "pro":    {1: 4900,  3: 13800, 12: 49800},
    "promax": {1: 9900,  3: 28800, 12: 98800},
}

# 会员按「份」售卖：每份 6 个月，买 x 份 = 6x 个月。
# 单价（分/份）= 原 12 月价 ÷ 2（买 2 份=12 月，总价等于原 12 月价）。
UNIT_MONTHS = 6
UNIT_PRICE_FEN: dict[str, int] = {
    "basic":  14400,
    "pro":    24900,
    "promax": 49400,
}

ALLOWED_TIERS = frozenset(PRICE_TABLE.keys())
ALLOWED_DURATIONS = frozenset({1, 3, 12})   # 遗留：兼容激活码等按月路径
ALLOWED_ORDER_TYPES = frozenset({"new", "renew", "upgrade"})


def get_price(tier: str, duration_months: int) -> int:
    """返回价格（分）；无效参数抛 AppError(400)。"""
    if tier not in PRICE_TABLE:
        raise AppError(code=400, message=f"无效档位：{tier}，可选：basic/pro/promax")
    if duration_months not in PRICE_TABLE[tier]:
        raise AppError(
            code=400,
            message=f"无效时长：{duration_months}，可选：1/3/12",
        )
    return PRICE_TABLE[tier][duration_months]


def get_unit_price(tier: str, quantity: int) -> int:
    """按份计价（分）：每份 6 个月。quantity 份 → 价格 = 单价×份数。"""
    if tier not in UNIT_PRICE_FEN:
        raise AppError(code=400, message=f"无效档位：{tier}，可选：basic/pro/promax")
    if quantity < 1 or quantity > 24:
        raise AppError(code=400, message="份数需在 1-24 之间")
    return UNIT_PRICE_FEN[tier] * quantity


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_order(
    db: AsyncSession,
    *,
    payer_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    tier: str,
    duration_months: int | None = None,
    quantity: int | None = None,          # 按份：每份 6 个月（优先于 duration_months）
    order_type: str,
    semesters: list[dict] | None = None,  # V2 新增
    addon_feature_key: str | None = None, # 加量包：购买某功能的加量次数
    is_promotional: bool = False,         # 活动价订单（不支持退款）
    payment_confirm_log_id: uuid.UUID | None = None,  # 支付确认留存（§4.6）
) -> Order:
    """会员下单。三种计价：V2 学期(semesters) > 按份(quantity,6月/份) > 遗留按月(duration_months)。
    调用方负责 commit。"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    order_no = f"ORD-{today}-{uuid.uuid4().hex[:8].upper()}"

    if addon_feature_key:
        # 加量包：金额取该功能加量配置价
        from app.services import entitlement_service
        acfg = await entitlement_service.addon_config(db, addon_feature_key)
        if not acfg["enabled"] or acfg["price_fen"] <= 0:
            raise AppError(code=400, message="该功能未开放加量包")
        order = Order(
            id=uuid.uuid4(), order_no=order_no, payer_id=payer_id,
            beneficiary_id=beneficiary_id, order_type=order_type, tier=tier,
            duration_months=0, amount_fen=acfg["price_fen"], status="pending",
            addon_feature_key=addon_feature_key,
            is_promotional=is_promotional,
            payment_confirm_log_id=payment_confirm_log_id,
        )
        db.add(order)
        await db.flush()
        return order

    if semesters:
        # V2：按学期计价
        from app.services.pricing_service import get_semester_pricing, calc_total_fen
        pricing = await get_semester_pricing(db)
        semester_count = len(semesters)
        amount_fen = calc_total_fen(pricing, tier=tier, semester_count=semester_count)
        order = Order(
            id=uuid.uuid4(),
            order_no=order_no,
            payer_id=payer_id,
            beneficiary_id=beneficiary_id,
            order_type=order_type,
            tier=tier,
            duration_months=0,  # V2 占位
            amount_fen=amount_fen,
            status="pending",
            semester_count=semester_count,
            purchased_semester_ids=semesters,
        )
    elif quantity is not None:
        # 按份：每份 6 个月，x 份 = 6x 月
        months = UNIT_MONTHS * quantity
        amount_fen = get_unit_price(tier, quantity)
        order = Order(
            id=uuid.uuid4(),
            order_no=order_no,
            payer_id=payer_id,
            beneficiary_id=beneficiary_id,
            order_type=order_type,
            tier=tier,
            duration_months=months,
            amount_fen=amount_fen,
            status="pending",
        )
    else:
        # 遗留：按月（1/3/12），兼容激活码等
        amount_fen = get_price(tier, duration_months)
        order = Order(
            id=uuid.uuid4(),
            order_no=order_no,
            payer_id=payer_id,
            beneficiary_id=beneficiary_id,
            order_type=order_type,
            tier=tier,
            duration_months=duration_months,
            amount_fen=amount_fen,
            status="pending",
        )
    # 退款相关通用字段（§4.5）：总天数用于按比例退款计算
    order.is_promotional = is_promotional
    order.payment_confirm_log_id = payment_confirm_log_id
    order.total_days = max((order.duration_months or 1) * 30, 1)
    db.add(order)
    await db.flush()
    return order


async def get_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Order | None:
    """按 id 查询订单；user_id 须为付款人或受益人（防越权）。"""
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            or_(Order.payer_id == user_id, Order.beneficiary_id == user_id),
        )
    )
    return result.scalar_one_or_none()


async def mark_order_paid(
    db: AsyncSession,
    *,
    order: Order,
    wx_transaction_id: str,
) -> Order:
    """标记订单已支付，写入微信流水号和支付时间。调用方负责 commit。"""
    order.status = "paid"
    order.wx_transaction_id = wx_transaction_id
    order.paid_at = datetime.now(timezone.utc)
    await db.flush()
    return order
