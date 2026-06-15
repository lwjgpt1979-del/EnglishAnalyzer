"""多收款主体 路由 + 按主体退款 + 默认唯一 tests。

自包含造数据（唯一前缀）+ finally 清理，并恢复全局默认收款主体。
"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "patest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _mk_user(db, city=None):
    uid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO users (id,openid,role,is_active,city_code) VALUES (:i,:o,'student',true,:c)"),
        {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}", "c": city})
    return uid


async def _mk_account(db, *, name, provider="wechat", config=None, alias=None,
                      branch_id=None, subject="company"):
    aid = uuid.uuid4()
    import json
    await db.execute(text(
        "INSERT INTO payment_accounts (id,name,subject_type,provider,config,secret_alias,branch_company_id,is_default,is_active) "
        "VALUES (:i,:n,:st,:p,CAST(:c AS JSONB),:a,:b,false,true)"),
        {"i": aid, "n": f"{_TAG}_{name}", "st": subject, "p": provider,
         "c": json.dumps(config or {}), "a": alias, "b": branch_id})
    return aid


async def _mk_branch_with_city(db, city):
    bid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO branch_companies (id,name,is_active) VALUES (:i,:n,true)"),
        {"i": bid, "n": f"{_TAG}_branch"})
    await db.execute(text(
        "INSERT INTO branch_company_cities (id,branch_company_id,city_code,effective_from) "
        "VALUES (:i,:b,:c,:f)"),
        {"i": uuid.uuid4(), "b": bid, "c": city, "f": dt.date(2020, 1, 1)})
    return bid


async def _cleanup(db, orig_default):
    await db.execute(text("DELETE FROM payment_accounts WHERE name LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text(
        "DELETE FROM branch_company_cities WHERE branch_company_id IN "
        "(SELECT id FROM branch_companies WHERE name LIKE :p)"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM branch_companies WHERE name LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    # 恢复全局默认收款主体（set_default 测试可能改动）
    if orig_default:
        await db.execute(text("UPDATE payment_accounts SET is_default=false WHERE is_default=true"))
        await db.execute(text("UPDATE payment_accounts SET is_default=true WHERE id=:i"), {"i": orig_default})
    await db.flush()


@pytest.mark.asyncio
async def test_multi_merchant_routing_and_refund():
    from app.services import payment_account_service as pa
    from app.models.d1_users import User

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        orig_default = await db.scalar(text("SELECT id FROM payment_accounts WHERE is_default=true"))
        try:
            # 子公司主体（关联分公司+城市）
            bid = await _mk_branch_with_city(db, "SH_TEST")
            sub_id = await _mk_account(db, name="sub_sh", config={"mch_id": "MCH_SUB"},
                                       alias="sub_sh", branch_id=bid, subject="subsidiary")
            await db.flush()

            # 1) 有城市归属 → 路由到子公司主体
            u_sh = await _mk_user(db, city="SH_TEST")
            acc = await pa.resolve_for_order(db, await db.get(User, u_sh))
            assert acc is not None and acc.id == sub_id

            # 2) 无城市 → 回退默认主体（全局 seed 的个体）
            u_none = await _mk_user(db, city=None)
            acc2 = await pa.resolve_for_order(db, await db.get(User, u_none))
            assert acc2 is not None and acc2.is_default is True

            # 3) 按主体取凭证：子公司 vs 默认，mch_id 不同
            creds_sub = pa.load_credentials(await db.get(type(acc), sub_id))
            creds_def = pa.load_credentials(acc2)
            assert creds_sub.mch_id == "MCH_SUB"
            assert creds_sub.mch_id != creds_def.mch_id

            # 4) 退款按订单固化主体取凭证（迁移兼容）：
            #    造两个"公司"主体模拟"个体→公司"，老订单仍指旧主体
            old_id = await _mk_account(db, name="old_indiv", config={"mch_id": "MCH_OLD"}, alias="old")
            new_id = await _mk_account(db, name="new_company", config={"mch_id": "MCH_NEW"}, alias="new")
            await db.flush()

            class _O:  # 轻量 order stub
                payment_account_id = old_id
            creds_for_old = await pa.resolve_creds_for_order(db, _O())
            assert creds_for_old.mch_id == "MCH_OLD"   # 老订单仍走旧主体

            # 5) set_default 唯一性：设 new 为默认 → 其余 default 取消
            await pa.set_default(db, new_id)
            await db.flush()
            cnt = await db.scalar(text("SELECT count(*) FROM payment_accounts WHERE is_default=true"))
            assert cnt == 1
            now_default = await db.scalar(text("SELECT id FROM payment_accounts WHERE is_default=true"))
            assert str(now_default) == str(new_id)
            # 老订单 stub 指 old，仍解析 old（不受默认切换影响）
            creds_after = await pa.resolve_creds_for_order(db, _O())
            assert creds_after.mch_id == "MCH_OLD"
        finally:
            await _cleanup(db, orig_default)
            await db.commit()
    await engine.dispose()
