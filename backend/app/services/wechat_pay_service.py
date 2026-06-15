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
_REFUND_URL = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"


def _is_dev_mode(creds=None) -> bool:
    """True 时无法真实 RSA 签名 → 走 dev-mock。

    creds 给定时按其 is_dev/私钥判定；否则回退全局 settings（兼容回调等单主体场景）。
    """
    if creds is not None:
        return bool(creds.is_dev) or not creds.private_key_pem \
            or creds.private_key_pem.startswith("placeholder")
    return settings.wechat_pay_private_key_pem.startswith("placeholder")


def _sign_rsa(message: str, private_key_pem: str | None = None) -> str:
    """RSA-SHA256 签名并 base64 编码。无真实私钥时返回占位字符串。"""
    pem = private_key_pem or settings.wechat_pay_private_key_pem
    if not pem or pem.startswith("placeholder"):
        return "dev_signature_placeholder"
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

    if "BEGIN" not in pem or "PRIVATE KEY" not in pem:
        raise AppError(code=400, message=(
            "商户私钥格式不正确：应填 apiclient_key.pem 文件内容"
            "（-----BEGIN PRIVATE KEY----- 开头），请在后台「收款主体→密钥」重新粘贴"))
    try:
        private_key = serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception as exc:
        raise AppError(code=400, message=(
            "商户私钥无法解析，请确认粘贴的是完整的 apiclient_key.pem 内容（含首尾行）"
        )) from exc
    sig = private_key.sign(message.encode(), asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _build_auth_header(method: str, url_path: str, body: str, creds) -> str:
    """构建微信支付 v3 Authorization 请求头（按 creds 商户）。"""
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    sig = _sign_rsa(message, creds.private_key_pem)
    return (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{creds.mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{sig}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{creds.cert_serial}"'
    )


async def get_prepay_id(order: Order, openid: str, creds) -> str:
    """调用微信支付 JSAPI 统一下单接口（按 creds 指定的收款主体），返回 prepay_id。

    异常：微信 API 返回错误 → AppError(2003)
    """
    body_dict = {
        "appid": creds.app_id,
        "mchid": creds.mch_id,
        "description": f"engGramer {order.tier}会员 {order.duration_months}个月",
        "out_trade_no": order.order_no,
        "notify_url": creds.notify_url or settings.wechat_pay_notify_url,
        "amount": {"total": order.amount_fen, "currency": "CNY"},
        "payer": {"openid": openid},
    }
    body_str = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    auth = _build_auth_header("POST", "/v3/pay/transactions/jsapi", body_str, creds)

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


def build_pay_params(prepay_id: str, creds) -> dict:
    """构建前端 wx.requestPayment() 所需的 5 个参数（按 creds 商户的 appid 签名）。"""
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    message = f"{creds.app_id}\n{timestamp}\n{nonce}\n{package}\n"
    pay_sign = _sign_rsa(message, creds.private_key_pem)
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


async def refund(creds, *, out_refund_no: str, amount_fen: int, total_fen: int,
                 transaction_id: str | None = None,
                 out_trade_no: str | None = None,
                 notify_url: str | None = None) -> str:
    """微信退款 v3（按 creds 指定的收款主体）。返回微信退款单号 refund_id。

    notify_url：退款结果异步通知地址（对账用）。
    dev-mock（无真实私钥）时只返回 mock 退款单号，不真调微信。
    """
    if _is_dev_mode(creds):
        return f"mock_refund_{uuid.uuid4().hex[:16]}"
    body_dict = {
        "out_refund_no": out_refund_no,
        "amount": {"refund": amount_fen, "total": total_fen, "currency": "CNY"},
    }
    if notify_url:
        body_dict["notify_url"] = notify_url
    if transaction_id:
        body_dict["transaction_id"] = transaction_id
    elif out_trade_no:
        body_dict["out_trade_no"] = out_trade_no
    body_str = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    auth = _build_auth_header("POST", "/v3/refund/domestic/refunds", body_str, creds)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _REFUND_URL, content=body_str.encode(),
                headers={"Authorization": auth, "Content-Type": "application/json",
                         "Accept": "application/json"},
            )
            data = resp.json()
    except Exception as exc:
        raise AppError(code=2003, message=f"微信退款请求失败：{exc}") from exc
    if "refund_id" not in data:
        raise AppError(code=2003, message=f"微信退款失败：{data.get('message', str(data))}")
    return data["refund_id"]


def verify_signature(headers: dict, raw_body: bytes, platform_public_key_pem: str) -> bool:
    """验证微信支付 v3 回调签名（RSA-SHA256/PKCS1v15，平台证书公钥）。

    构造待验签串 = f"{timestamp}\n{nonce}\n{body}\n"，对 Wechatpay-Signature
    (base64) 用平台公钥验签。headers 大小写不敏感。
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.exceptions import InvalidSignature

    h = {k.lower(): v for k, v in headers.items()}
    timestamp = h.get("wechatpay-timestamp", "")
    nonce = h.get("wechatpay-nonce", "")
    signature_b64 = h.get("wechatpay-signature", "")
    if not (timestamp and nonce and signature_b64):
        return False
    message = f"{timestamp}\n{nonce}\n{raw_body.decode()}\n".encode()
    try:
        pub = serialization.load_pem_public_key(platform_public_key_pem.encode())
        pub.verify(
            base64.b64decode(signature_b64), message,
            asym_padding.PKCS1v15(), hashes.SHA256(),
        )
        return True
    except (InvalidSignature, Exception):
        return False


def verify_and_decrypt_callback(headers: dict, raw_body: bytes, creds=None) -> dict:
    """验证微信回调签名并解密 resource 字段，返回解密后的交易数据。

    - 测试辅助：resource 含 mock_decrypted 字段时直接返回，无需 AES-GCM。
    - dev（creds.is_dev 或 skip_sig_verify=True）跳过 RSA 验签。
    - 生产：用 creds.platform_public_key_pem 验证 Wechatpay-Signature；
      再用 creds.api_key_v3（前 32 字节）AES-256-GCM 解密 resource。
    creds 为空时回退全局 settings（兼容单商户）。
    """
    body = json.loads(raw_body)
    resource = body.get("resource", {})

    # 测试辅助快捷路径
    if "mock_decrypted" in resource:
        return resource["mock_decrypted"]

    api_key = (creds.api_key_v3 if creds and creds.api_key_v3
               else settings.wechat_pay_api_key_v3)
    plat_pem = creds.platform_public_key_pem if creds else None
    is_dev = bool(creds and creds.is_dev)

    # 生产验签（dev 或显式跳过时不验）
    if not is_dev and not settings.wechat_pay_skip_sig_verify:
        if not plat_pem:
            raise AppError(code=400, message="缺少微信平台证书公钥，无法验签回调")
        if not verify_signature(headers, raw_body, plat_pem):
            raise AppError(code=400, message="微信回调验签失败")

    # AES-256-GCM 解密 resource
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = api_key.encode()[:32]
        nonce_bytes = resource["nonce"].encode()
        associated_data = resource.get("associated_data", "").encode()
        ciphertext = base64.b64decode(resource["ciphertext"])
        plaintext = AESGCM(key).decrypt(nonce_bytes, ciphertext, associated_data)
        return json.loads(plaintext)
    except Exception as exc:
        raise AppError(code=400, message=f"微信回调解密失败：{exc}") from exc
