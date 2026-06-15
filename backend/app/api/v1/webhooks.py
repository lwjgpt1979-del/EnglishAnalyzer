"""微信支付回调 Webhook。

微信服务器调用此接口，不需要 JWT 鉴权。
必须在 5 秒内返回 {"code": "SUCCESS"}，否则微信会重试（最多 15 次）。

多收款主体：每个主体可配独立 notify_url。默认主体走 /wx-pay；
非默认主体走 /wx-pay/{account_id}，以便按主体取 APIv3 key 解密、平台证书验签。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.models.d2_payments import Order
from app.services import (
    membership_service, order_service, payment_account_service, wechat_pay_service,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _handle_wx_pay(request: Request, db: AsyncSession,
                         account_id: uuid.UUID | None) -> dict:
    """支付结果通知公共处理：按主体取凭证验签解密 → 标记已支付 → 激活会员。"""
    raw_body = await request.body()
    headers = dict(request.headers)

    # 取该回调对应收款主体的凭证（用于验签 + 解密）
    account = None
    if account_id is not None:
        account = await payment_account_service.get(db, account_id)
    if account is None:
        account = await payment_account_service.get_default(db)
    creds = payment_account_service.load_credentials(account)

    try:
        decrypted = wechat_pay_service.verify_and_decrypt_callback(headers, raw_body, creds)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(code=400, message=f"回调处理失败：{exc}") from exc

    if decrypted.get("trade_state") != "SUCCESS":
        return {"code": "SUCCESS"}

    out_trade_no = decrypted.get("out_trade_no", "")
    wx_transaction_id = decrypted.get("transaction_id", "")

    result = await db.execute(select(Order).where(Order.order_no == out_trade_no))
    order = result.scalar_one_or_none()
    if order is None:
        raise AppError(code=404, message=f"订单不存在：{out_trade_no}")

    if order.status == "paid":  # 幂等
        return {"code": "SUCCESS"}

    await order_service.mark_order_paid(db, order=order, wx_transaction_id=wx_transaction_id)
    await membership_service.activate_membership(db, order=order)
    await db.commit()
    return {"code": "SUCCESS"}


@router.post("/wx-pay")
async def wx_pay_callback(request: Request, db: DbDep):
    """默认收款主体的支付结果通知。"""
    return await _handle_wx_pay(request, db, None)


@router.post("/wx-pay/{account_id}")
async def wx_pay_callback_for_account(account_id: uuid.UUID, request: Request, db: DbDep):
    """指定收款主体（子公司/多商户）的支付结果通知。"""
    return await _handle_wx_pay(request, db, account_id)


async def _handle_wx_refund(request: Request, db: AsyncSession,
                            account_id: uuid.UUID | None) -> dict:
    """退款结果通知：按主体取凭证验签解密 → 按 out_refund_no 对账更新。"""
    from app.services import refund_service
    raw_body = await request.body()
    headers = dict(request.headers)
    account = None
    if account_id is not None:
        account = await payment_account_service.get(db, account_id)
    if account is None:
        account = await payment_account_service.get_default(db)
    creds = payment_account_service.load_credentials(account)
    try:
        decrypted = wechat_pay_service.verify_and_decrypt_callback(headers, raw_body, creds)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(code=400, message=f"退款回调处理失败：{exc}") from exc
    await refund_service.handle_refund_notify(db, decrypted)
    await db.commit()
    return {"code": "SUCCESS"}


@router.post("/wx-refund")
async def wx_refund_callback(request: Request, db: DbDep):
    """默认收款主体的退款结果通知（对账）。"""
    return await _handle_wx_refund(request, db, None)


@router.post("/wx-refund/{account_id}")
async def wx_refund_callback_for_account(account_id: uuid.UUID, request: Request, db: DbDep):
    """指定收款主体的退款结果通知（对账）。"""
    return await _handle_wx_refund(request, db, account_id)
