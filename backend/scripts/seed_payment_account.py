"""种子：默认收款主体 + 回填存量订单（多收款主体地基，阶段①=个体）。

部署/升级到 m56 后执行一次（幂等）：
  cd backend && DATABASE_URL=... python -m scripts.seed_payment_account

阶段②成立公司后：在后台「收款主体」新增公司主体并「设默认」即可，无需改代码。
密钥仍由运维写入 env（PAY__<alias>__<KEY>），本脚本不接触密钥。
"""
import asyncio
import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def main() -> None:
    eng = create_async_engine(settings.async_database_url)
    async with eng.begin() as c:
        did = (await c.execute(
            text("SELECT id FROM payment_accounts WHERE is_default=true"))).scalar()
        if not did:
            did = uuid.uuid4()
            cfg = {
                "mch_id": settings.wechat_pay_mch_id,
                "cert_serial": settings.wechat_pay_cert_serial,
                "app_id": settings.wechat_appid,
            }
            await c.execute(text(
                "INSERT INTO payment_accounts "
                "(id,name,subject_type,provider,config,secret_alias,is_default,is_active) "
                "VALUES (:i,:n,'individual','wechat',CAST(:cfg AS JSONB),'legacy_wechat',true,true)"
            ), {"i": did, "n": "个体工商户（默认收款主体）", "cfg": json.dumps(cfg)})
            print(f"seeded default account: {did}")
        else:
            print(f"default account exists: {did}")
        res = await c.execute(text(
            "UPDATE orders SET payment_account_id=:d WHERE payment_account_id IS NULL"
        ), {"d": did})
        print(f"backfilled orders: {res.rowcount}")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
