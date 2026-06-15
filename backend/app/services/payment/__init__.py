"""支付渠道适配器层（provider-agnostic）。

按 PaymentAccount.provider 分发到对应适配器，核心下单/退款逻辑不碰具体渠道。
新增渠道 = 新增一个适配器并 register，无需改动核心。
"""
from .base import Creds, PaymentProvider, get_provider, register  # noqa: F401

# 注册内置适配器（import 即注册）
from . import wechat as _wechat  # noqa: F401,E402
from . import alipay as _alipay  # noqa: F401,E402
from . import apple_iap as _apple  # noqa: F401,E402
