"""苹果 App 内购买（IAP）适配器（预留桩）。

与微信/支付宝不同：
- create_payment 由客户端 StoreKit 发起，服务端只做收据校验（待接入）。
- refund 由苹果发起并通过 Server Notifications 回调，**服务端不主动退款**，
  这里实现为"不主动调用、仅记账/对账"，由回调更新状态。
"""
from __future__ import annotations

from app.core.exceptions import AppError
from .base import Creds, PaymentProvider, register


class AppleIapProvider(PaymentProvider):
    code = "apple_iap"

    async def create_payment(self, order, creds: Creds, *, openid: str | None = None) -> dict:
        # IAP 走客户端 StoreKit；服务端返回标识，由客户端发起内购后回传收据校验
        return {"provider": "apple_iap", "out_trade_no": order.order_no,
                "note": "由客户端 StoreKit 发起内购，服务端校验收据（待接入）"}

    async def refund(self, creds: Creds, *, out_refund_no: str, amount_fen: int,
                     total_fen: int, transaction_id: str | None = None,
                     out_trade_no: str | None = None,
                     notify_url: str | None = None) -> str:
        # 苹果退款由用户向 Apple 申请、Apple 审批后回调；服务端不能主动发起
        raise AppError(
            code=400,
            message="苹果 IAP 退款由 App Store 处理，请引导用户通过 Apple 申请；"
                    "系统将依据苹果退款通知自动入账（对账，非主动退款）")

    def required_secret_keys(self) -> list[str]:
        return ["APPLE_IAP_ISSUER_ID", "APPLE_IAP_KEY_ID", "APPLE_IAP_PRIVATE_KEY_P8"]


register(AppleIapProvider())
