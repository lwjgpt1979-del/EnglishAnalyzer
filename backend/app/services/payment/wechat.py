"""微信支付适配器（包装现有 wechat_pay_service）。"""
from __future__ import annotations

from app.services import wechat_pay_service as wx
from .base import Creds, PaymentProvider, register


class WeChatProvider(PaymentProvider):
    code = "wechat"

    async def create_payment(self, order, creds: Creds, *, openid: str | None = None) -> dict:
        prepay_id = await wx.get_prepay_id(order, openid, creds)
        return wx.build_pay_params(prepay_id, creds)

    async def refund(self, creds: Creds, *, out_refund_no: str, amount_fen: int,
                     total_fen: int, transaction_id: str | None = None,
                     out_trade_no: str | None = None,
                     notify_url: str | None = None) -> str:
        return await wx.refund(
            creds, out_refund_no=out_refund_no, amount_fen=amount_fen,
            total_fen=total_fen, transaction_id=transaction_id,
            out_trade_no=out_trade_no, notify_url=notify_url)

    def required_secret_keys(self) -> list[str]:
        # 私钥=请求签名；APIv3=回调解密；平台公钥=回调验签（三件套）
        return ["WECHAT_PRIVATE_KEY_PEM", "WECHAT_API_KEY_V3",
                "WECHAT_PLATFORM_PUBLIC_KEY_PEM"]


register(WeChatProvider())
