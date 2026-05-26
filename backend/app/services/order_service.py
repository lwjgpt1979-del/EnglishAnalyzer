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

ALLOWED_TIERS = frozenset(PRICE_TABLE.keys())
ALLOWED_DURATIONS = frozenset({1, 3, 12})
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


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_order(
    db: AsyncSession,
    *,
    payer_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    tier: str,
    duration_months: int,
    order_type: str,
) -> Order:
    """创建待支付订单（status=pending）。调用方负责 commit。"""
    amount_fen = get_price(tier, duration_months)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    order_no = f"ORD-{today}-{uuid.uuid4().hex[:8].upper()}"

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
