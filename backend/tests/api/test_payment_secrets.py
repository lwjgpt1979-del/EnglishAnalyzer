"""字段加密 + 收款主体密钥加密入库 tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "secrettest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


def test_crypto_roundtrip_and_format():
    from app.core import crypto
    token = crypto.encrypt("my-private-key-pem")
    assert token.startswith("v1:")
    assert token != "my-private-key-pem"            # 不是明文
    assert crypto.decrypt(token) == "my-private-key-pem"
    # 两次加密同一明文，密文不同（随机 nonce）
    assert crypto.encrypt("x") != crypto.encrypt("x")
    # 非本格式（历史明文）原样返回
    assert crypto.decrypt("plain") == "plain"


@pytest.mark.asyncio
async def test_set_secrets_encrypted_and_loaded():
    from app.services import payment_account_service as pa
    from app.models.d10_branch import PaymentAccount
    from app.core import crypto

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        aid = uuid.uuid4()
        try:
            await db.execute(text(
                "INSERT INTO payment_accounts (id,name,subject_type,provider,config,is_default,is_active) "
                "VALUES (:i,:n,'company','wechat',CAST('{\"mch_id\":\"M1\"}' AS JSONB),false,true)"),
                {"i": aid, "n": f"{_TAG}_acc"})
            await db.flush()

            # 录入密钥 → 加密存库
            await pa.set_secrets(db, aid, {
                "WECHAT_PRIVATE_KEY_PEM": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----",
                "WECHAT_API_KEY_V3": "k" * 32,
                "WECHAT_PLATFORM_PUBLIC_KEY_PEM": "-----BEGIN PUBLIC KEY-----\nXYZ\n-----END PUBLIC KEY-----",
            })
            await db.flush()

            acc = await db.get(PaymentAccount, aid)
            # 库里是密文，不是明文
            raw = acc.secrets_enc["WECHAT_API_KEY_V3"]
            assert raw.startswith("v1:") and raw != "k" * 32

            # load_credentials 解密还原
            creds = pa.load_credentials(acc)
            assert creds.api_key_v3 == "k" * 32
            assert creds.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
            assert creds.platform_public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
            assert creds.is_dev is False           # 有真实私钥 → 非 dev
            assert creds.mch_id == "M1"

            # 展示项含 secrets_set 布尔，且不含密钥值
            item = pa._to_item(acc)
            assert item["secrets_set"]["WECHAT_API_KEY_V3"] is True
            assert item["credentials_ready"] is True
            assert "k" * 32 not in str(item)       # 绝不泄露明文

            # 删除某密钥（空值）
            await pa.set_secrets(db, aid, {"WECHAT_API_KEY_V3": ""})
            await db.flush()
            acc2 = await db.get(PaymentAccount, aid)
            assert "WECHAT_API_KEY_V3" not in (acc2.secrets_enc or {})
        finally:
            await db.execute(text("DELETE FROM payment_accounts WHERE name LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
