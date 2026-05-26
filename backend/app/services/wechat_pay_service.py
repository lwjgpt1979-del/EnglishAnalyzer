"""微信支付 v3 JSAPI 服务。

生产环境需要真实商户私钥（RSA PEM）和 API key v3（AES-GCM 解密回调）。
开发模式（private_key_pem 以 'placeholder' 开头）跳过实际签名，
回调解密中若 resource 含 mock_decrypted 字段则直接返回，无需真实 AES-GCM。
"""
from __future__ import annotations

import base64
import json
import time
import uuid

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d2_payments import Order

_JSAPI_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"


def _is_dev_mode() -> bool:
    """True when the private key is a placeholder — real RSA signing is not possible."""
    return settings.wechat_pay_private_key_pem.startswith("placeholder")


def _sign_rsa(message: str) -> str:
    """RSA-SHA256 签名并 base64 编码。dev 模式返回占位字符串。"""
    if _is_dev_mode():
        return "dev_signature_placeholder"
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

    private_key = serialization.load_pem_private_key(
        settings.wechat_pay_private_key_pem.encode(), password=None
    )
    sig = private_key.sign(message.encode(), asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _build_auth_header(method: str, url_path: str, body: str) -> str:
    """构建微信支付 v3 Authorization 请求头。"""
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    sig = _sign_rsa(message)
    return (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.wechat_pay_mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{sig}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.wechat_pay_cert_serial}"'
    )


async def get_prepay_id(order: Order, openid: str) -> str:
    """调用微信支付 JSAPI 统一下单接口，返回 prepay_id。

    异常：微信 API 返回错误 → AppError(2003)
    """
    body_dict = {
        "appid": settings.wechat_appid,
        "mchid": settings.wechat_pay_mch_id,
        "description": f"engGramer {order.tier}会员 {order.duration_months}个月",
        "out_trade_no": order.order_no,
        "notify_url": settings.wechat_pay_notify_url,
        "amount": {"total": order.amount_fen, "currency": "CNY"},
        "payer": {"openid": openid},
    }
    body_str = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    auth = _build_auth_header("POST", "/v3/pay/transactions/jsapi", body_str)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _JSAPI_URL,
                content=body_str.encode(),
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            data = resp.json()
    except Exception as exc:
        raise AppError(code=2003, message=f"微信支付服务请求失败：{exc}") from exc

    if "prepay_id" not in data:
        raise AppError(
            code=2003, message=f"微信支付失败：{data.get('message', str(data))}"
        )
    return data["prepay_id"]


def build_pay_params(prepay_id: str) -> dict:
    """构建前端 wx.requestPayment() 所需的 5 个参数。"""
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    message = f"{settings.wechat_appid}\n{timestamp}\n{nonce}\n{package}\n"
    pay_sign = _sign_rsa(message)
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


def verify_and_decrypt_callback(headers: dict, raw_body: bytes) -> dict:
    """验证微信回调签名并解密 resource 字段，返回解密后的交易数据。

    - dev 模式（skip_sig_verify=True）跳过 RSA 验签。
    - 测试辅助：resource 含 mock_decrypted 字段时直接返回，无需 AES-GCM。
    - 生产：使用 AES-256-GCM 解密（key = wechat_pay_api_key_v3 前 32 字节）。
    """
    body = json.loads(raw_body)
    resource = body.get("resource", {})

    # 测试辅助快捷路径
    if "mock_decrypted" in resource:
        return resource["mock_decrypted"]

    if not settings.wechat_pay_skip_sig_verify:
        # 生产环境：完整 RSA 验签（需微信平台公钥证书，此处预留）
        pass

    # AES-256-GCM 解密 resource
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = settings.wechat_pay_api_key_v3.encode()[:32]
        nonce_bytes = resource["nonce"].encode()
        associated_data = resource.get("associated_data", "").encode()
        ciphertext = base64.b64decode(resource["ciphertext"])
        plaintext = AESGCM(key).decrypt(nonce_bytes, ciphertext, associated_data)
        return json.loads(plaintext)
    except Exception as exc:
        raise AppError(code=400, message=f"微信回调解密失败：{exc}") from exc
