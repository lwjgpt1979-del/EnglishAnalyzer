"""支付宝适配器（预留桩）。dev-mock 可走通流程；真实对接待接入。"""
from __future__ import annotations

import uuid

from app.core.exceptions import AppError
from .base import Creds, PaymentProvider, register


class AlipayProvider(PaymentProvider):
    code = "alipay"

    async def create_payment(self, order, creds: Creds, *, openid: str | None = None) -> dict:
        if creds.is_dev:
            return {"provider": "alipay", "mock": True, "out_trade_no": order.order_no}
        raise AppError(code=400, message="支付宝支付待接入（P-后续）")

    async def refund(self, creds: Creds, *, out_refund_no: str, amount_fen: int,
                     total_fen: int, transaction_id: str | None = None,
                     out_trade_no: str | None = None) -> str:
        if creds.is_dev:
            return f"mock_alipay_refund_{uuid.uuid4().hex[:16]}"
        raise AppError(code=400, message="支付宝退款待接入（P-后续）")

    def required_secret_keys(self) -> list[str]:
        return ["ALIPAY_PRIVATE_KEY", "ALIPAY_PUBLIC_KEY"]


register(AlipayProvider())
