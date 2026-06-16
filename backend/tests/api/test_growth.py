"""增长分析（§5.5）：渠道来源 / 续费率 / 漏斗 tests。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "growthtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_channel_renewal_funnel():
    from app.services import growth_service as g

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        now = dt.datetime.now(dt.timezone.utc)
        uids = [uuid.uuid4() for _ in range(3)]
        # 3 个学生，渠道 school/school/referral
        chans = ["school", "school", "referral"]
        for u, c in zip(uids, chans):
            await db.execute(text(
                "INSERT INTO users (id,openid,role,is_active,acquisition_channel) "
                "VALUES (:i,:o,'student',true,:c)"),
                {"i": u, "o": f"{_TAG}_{u.hex[:8]}", "c": c})
        # 一个 pro 会员，近 90 天内到期（续费机会）
        mid = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO memberships (id,user_id,tier,started_at,expires_at,is_active) "
            "VALUES (:i,:u,'pro',:s,:e,false)"),
            {"i": mid, "u": uids[0], "s": now - dt.timedelta(days=180),
             "e": now - dt.timedelta(days=5)})
        # 一笔已支付 pro 续费订单（近窗口）
        oid = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,"
            "duration_months,amount_fen,status,paid_at) "
            "VALUES (:i,:no,:u,:u,'renew','pro',6,10000,'paid',:p)"),
            {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "u": uids[0],
             "p": now - dt.timedelta(days=2)})
        await db.flush()
        try:
            # 渠道分布
            ch = await g.channel_distribution(db)
            by = {x["channel"]: x["count"] for x in ch["items"]}
            assert by.get("school", 0) >= 2 and by.get("referral", 0) >= 1

            # 续费率：pro 至少 1 到期 1 续费 → rate>0
            rr = await g.renewal_rate(db, days=90)
            pro = next(x for x in rr["by_tier"] if x["tier"] == "pro")
            assert pro["expiring"] >= 1 and pro["renewed"] >= 1 and pro["rate_pct"] > 0

            # 漏斗：注册≥3，付费/续费阶段含本测试用户
            fn = await g.funnel(db)
            stages = {s["key"]: s["count"] for s in fn["stages"]}
            assert stages["registered"] >= 3
            assert stages["paid"] >= 1 and stages["renewed"] >= 1
            # 每阶段都带两种转化率
            assert all("pct_of_registered" in s and "pct_of_prev" in s for s in fn["stages"])
        finally:
            await db.execute(text("DELETE FROM orders WHERE id=:o"), {"o": oid})
            await db.execute(text("DELETE FROM memberships WHERE id=:m"), {"m": mid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
