"""字段级加密（AES-256-GCM）。

用于把敏感字段（支付密钥、银行账户等）以密文存库：明文永不落库。
主密钥（KEK）来自 settings.field_encryption_key（env FIELD_ENCRYPTION_KEY），
全系统仅此一个根密钥；留空时 dev 回退派生自 jwt_secret_key（仅本地开发）。

密文格式：base64( nonce(12B) || ciphertext||tag )，前缀 "v1:" 便于日后换算法。
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_PREFIX = "v1:"


def _key() -> bytes:
    """返回 32 字节主密钥。"""
    raw = settings.field_encryption_key or ""
    if raw:
        try:
            k = base64.b64decode(raw)
            if len(k) >= 32:
                return k[:32]
        except Exception:
            pass
        # 非 base64 或长度不足：哈希成 32 字节（容错）
        return hashlib.sha256(raw.encode()).digest()
    # dev 回退：派生自 jwt_secret_key（仅本地开发，生产必须配 FIELD_ENCRYPTION_KEY）
    return hashlib.sha256(("fek:" + settings.jwt_secret_key).encode()).digest()


def is_dev_key() -> bool:
    """True 表示用的是 dev 回退主密钥（未配 FIELD_ENCRYPTION_KEY）。"""
    return not settings.field_encryption_key


def encrypt(plaintext: str) -> str:
    """加密明文 → 带前缀的 base64 密文。"""
    if plaintext is None:
        raise ValueError("plaintext is None")
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    """解密密文 → 明文。非本格式（无前缀）原样返回（兼容历史明文，慎用）。"""
    if not token:
        return token
    if not token.startswith(_PREFIX):
        return token
    blob = base64.b64decode(token[len(_PREFIX):])
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(_key()).decrypt(nonce, ct, None).decode()
