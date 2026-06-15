"""微信支付回调验签 + 解密 单测（自生成 RSA 密钥对，无需真实微信）。"""
from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services import wechat_pay_service as wx
from app.services.payment.base import Creds


def _keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub_pem


def _sign(priv, timestamp, nonce, body: bytes) -> str:
    msg = f"{timestamp}\n{nonce}\n{body.decode()}\n".encode()
    sig = priv.sign(msg, asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def test_verify_signature_ok_and_tampered():
    priv, pub_pem = _keypair()
    body = b'{"id":"evt_1","resource":{}}'
    ts, nonce = "1700000000", "abc123"
    sig = _sign(priv, ts, nonce, body)
    headers = {
        "Wechatpay-Timestamp": ts,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Signature": sig,
    }
    # 正确签名 → 通过
    assert wx.verify_signature(headers, body, pub_pem) is True
    # 篡改 body → 失败
    assert wx.verify_signature(headers, b'{"id":"evt_X"}', pub_pem) is False
    # 缺签名头 → 失败
    assert wx.verify_signature({}, body, pub_pem) is False


def test_verify_and_decrypt_callback_full():
    priv, pub_pem = _keypair()
    api_key = "x" * 32  # APIv3 key（32 字节）
    plaintext = json.dumps({"trade_state": "SUCCESS", "out_trade_no": "ORD-1",
                            "transaction_id": "wx_txn_1"}).encode()
    nonce12 = b"123456789012"
    associated = b"transaction"
    ciphertext = AESGCM(api_key.encode()[:32]).encrypt(nonce12, plaintext, associated)
    resource = {
        "nonce": nonce12.decode(),
        "associated_data": associated.decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    body = json.dumps({"id": "evt", "resource": resource}).encode()
    ts, n = "1700000001", "nonce-xyz"
    headers = {
        "Wechatpay-Timestamp": ts, "Wechatpay-Nonce": n,
        "Wechatpay-Signature": _sign(priv, ts, n, body),
    }
    creds = Creds(provider="wechat", is_dev=False, api_key_v3=api_key,
                  platform_public_key_pem=pub_pem)

    # 关闭全局 skip 以走真实验签路径
    from app.core.config import settings
    old = settings.wechat_pay_skip_sig_verify
    settings.wechat_pay_skip_sig_verify = False
    try:
        out = wx.verify_and_decrypt_callback(headers, body, creds)
        assert out["trade_state"] == "SUCCESS" and out["out_trade_no"] == "ORD-1"
        # 篡改签名 → 验签失败抛错
        bad = dict(headers, **{"Wechatpay-Signature": base64.b64encode(b"bad").decode()})
        import pytest
        from app.core.exceptions import AppError
        with pytest.raises(AppError):
            wx.verify_and_decrypt_callback(bad, body, creds)
    finally:
        settings.wechat_pay_skip_sig_verify = old
