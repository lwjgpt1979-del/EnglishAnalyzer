"""支付适配器协议 + 注册表。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.exceptions import AppError


@dataclass
class Creds:
    """某收款主体在某渠道下的运行时凭证（非密来自 DB config，密钥来自 env）。"""
    provider: str
    is_dev: bool = True            # True → dev-mock，不真调渠道
    account_id: str | None = None  # 收款主体 id（用于回调路由）
    app_id: str | None = None
    mch_id: str | None = None
    cert_serial: str | None = None
    private_key_pem: str | None = None
    api_key_v3: str | None = None
    platform_public_key_pem: str | None = None  # 微信平台证书公钥，用于回调验签
    notify_url: str | None = None
    extra: dict = field(default_factory=dict)   # 渠道专属（如苹果 issuer_id/key_id）


class PaymentProvider:
    """支付渠道适配器基类。各渠道实现自己的下单/退款/回调/密钥声明。"""
    code: str = "base"

    async def create_payment(self, order, creds: Creds, *, openid: str | None = None) -> dict:
        """创建支付，返回前端发起支付所需参数。"""
        raise NotImplementedError

    async def refund(self, creds: Creds, *, out_refund_no: str, amount_fen: int,
                     total_fen: int, transaction_id: str | None = None,
                     out_trade_no: str | None = None,
                     notify_url: str | None = None) -> str:
        """执行退款，返回渠道退款单号。

        注意：苹果IAP/GooglePlay 退款由商店发起并回调，适配器实现为"不主动调用、
        仅记账/对账"，由商店通知更新状态——同一退款引擎、不同适配器行为。
        """
        raise NotImplementedError

    def required_secret_keys(self) -> list[str]:
        """该渠道需要的 env 密钥名（用于后台"密钥就绪"探测）。"""
        return []


_REGISTRY: dict[str, PaymentProvider] = {}


def register(provider: PaymentProvider) -> None:
    _REGISTRY[provider.code] = provider


def get_provider(code: str) -> PaymentProvider:
    p = _REGISTRY.get(code)
    if p is None:
        raise AppError(code=400, message=f"未支持的支付渠道：{code}")
    return p


def required_secret_keys(code: str) -> list[str]:
    p = _REGISTRY.get(code)
    return p.required_secret_keys() if p else []
