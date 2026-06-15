"""财务管理：营收统计 + 分成结算 tests（§5.4）。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "fintest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_revenue_summary_and_settlement():
    from app.services import finance_service as fin

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(now.year, now.month, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(now.year + (now.month // 12), (now.month % 12) + 1, 1, tzinfo=dt.timezone.utc)
    async with sf() as db:
        uid = uuid.uuid4()
        bid = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
        await db.execute(text(
            "INSERT INTO branch_companies (id,name,is_active,commission_rate) VALUES (:i,:n,true,0.3)"),
            {"i": bid, "n": f"{_TAG}_branch"})
        paid = now - dt.timedelta(days=1)
        # 两笔已支付订单(归该分公司),共 300 元;一笔退 100
        o1, o2 = uuid.uuid4(), uuid.uuid4()
        for oid, amt in ((o1, 20000), (o2, 10000)):
            await db.execute(text(
                "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,duration_months,amount_fen,status,paid_at,branch_company_id) "
                "VALUES (:i,:no,:u,:u,'new','pro',6,:amt,'paid',:pa,:b)"),
                {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "u": uid, "amt": amt, "pa": paid, "b": bid})
        await db.execute(text(
            "INSERT INTO refund_records (id,order_id,amount_fen,refund_type,status,reviewed_at) "
            "VALUES (:i,:oid,10000,'standard_7d','completed',:t)"),
            {"i": uuid.uuid4(), "oid": o1, "t": paid})
        await db.flush()
        try:
            # 营收统计(按分公司)
            s = await fin.revenue_summary(db, start=start, end=end, group_by="branch")
            grp = [g for g in s["groups"] if g["key"] == str(bid)][0]
            assert grp["gross_yuan"] == 300.0 and grp["refund_yuan"] == 100.0 and grp["net_yuan"] == 200.0
            assert grp["orders"] == 2 and grp["refunds"] == 1

            # 分成结算:净 200 × 0.3 = 60 分公司应得, 平台 140
            st = await fin.compute_settlement(
                db, branch_id=bid, start=start.date(), end=end.date(), persist=True)
            assert st["net_yuan"] == 200.0 and st["branch_payable_yuan"] == 60.0
            assert st["platform_share_yuan"] == 140.0 and st.get("persisted")

            lst = await fin.list_settlements(db, branch_id=bid)
            assert len(lst) == 1 and lst[0]["branch_payable_yuan"] == 60.0

            # CSV 导出含订单号
            csv_text = await fin.export_orders_csv(db, start=start, end=end)
            assert f"ORD-{_TAG}-" in csv_text
        finally:
            await db.execute(text("DELETE FROM branch_settlements WHERE branch_company_id=:b"), {"b": bid})
            await db.execute(text("DELETE FROM refund_records WHERE order_id IN (SELECT id FROM orders WHERE order_no LIKE :p)"), {"p": f"ORD-{_TAG}-%"})
            await db.execute(text("DELETE FROM orders WHERE order_no LIKE :p"), {"p": f"ORD-{_TAG}-%"})
            await db.execute(text("DELETE FROM branch_companies WHERE name LIKE :p"), {"p": f"{_TAG}_%"})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
