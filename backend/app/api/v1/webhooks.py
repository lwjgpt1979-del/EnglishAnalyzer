"""微信支付回调 Webhook。

微信服务器调用此接口，不需要 JWT 鉴权。
必须在 5 秒内返回 {"code": "SUCCESS"}，否则微信会重试（最多 15 次）。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.models.d2_payments import Order
from app.services import membership_service, order_service, wechat_pay_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/wx-pay")
async def wx_pay_callback(request: Request, db: DbDep):
    """接收微信支付结果通知。

    处理逻辑：
    1. 验签 + 解密 resource（dev 模式跳过验签，支持 mock_decrypted 快捷路径）
    2. 只处理 trade_state=SUCCESS 的事件
    3. 幂等检查（order.status == paid 时直接返回 SUCCESS）
    4. 更新 order.status=paid，写入 wx_transaction_id + paid_at
    5. 激活 / 续费 / 升级会员
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    try:
        decrypted = wechat_pay_service.verify_and_decrypt_callback(headers, raw_body)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(code=400, message=f"回调处理失败：{exc}") from exc

    # 只处理支付成功事件
    if decrypted.get("trade_state") != "SUCCESS":
        return {"code": "SUCCESS"}

    out_trade_no = decrypted.get("out_trade_no", "")
    wx_transaction_id = decrypted.get("transaction_id", "")

    # 查找订单
    result = await db.execute(select(Order).where(Order.order_no == out_trade_no))
    order = result.scalar_one_or_none()
    if order is None:
        raise AppError(code=404, message=f"订单不存在：{out_trade_no}")

    # 幂等检查
    if order.status == "paid":
        return {"code": "SUCCESS"}

    # 更新订单状态
    await order_service.mark_order_paid(
        db, order=order, wx_transaction_id=wx_transaction_id
    )

    # 激活 / 续费 / 升级会员
    await membership_service.activate_membership(db, order=order)

    await db.commit()
    return {"code": "SUCCESS"}
