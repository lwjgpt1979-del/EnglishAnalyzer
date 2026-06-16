"""退款/申诉 SLA 超时告警 tests（§4.5.3）。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "slatest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_sla_overdue_and_alert():
    from app.services import refund_service as rs

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid, aid, oid, rid = (uuid.uuid4() for _ in range(4))
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=4)
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:8]}"})
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": aid, "o": f"{_TAG}_adm_{aid.hex[:8]}"})
        await db.execute(text(
            "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,duration_months,amount_fen,status) "
            "VALUES (:i,:no,:u,:u,'new','pro',6,10000,'paid')"),
            {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "u": uid})
        # 4 天前的待处理按比例退款 → 超 SLA(3天)
        await db.execute(text(
            "INSERT INTO refund_records (id,order_id,amount_fen,refund_type,status,created_at) "
            "VALUES (:i,:oid,5000,'prorated','pending',:c)"),
            {"i": rid, "oid": oid, "c": old})
        await db.flush()
        try:
            od = await rs.find_overdue(db)
            mine = [x for x in od if x["id"] == str(rid)]
            assert mine and mine[0]["days_overdue"] >= 3

            res = await rs.run_sla_alerts(db)
            assert res["overdue"] >= 1 and res["admins_notified"] >= 1
            # 该管理员收到 system 告警
            cnt = await db.scalar(text(
                "SELECT count(*) FROM notifications WHERE user_id=:a AND type='system' "
                "AND title LIKE '%超时未处理%'"), {"a": aid})
            assert cnt >= 1
        finally:
            await db.execute(text("DELETE FROM notifications WHERE user_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM refund_records WHERE id=:r"), {"r": rid})
            await db.execute(text("DELETE FROM orders WHERE id=:o"), {"o": oid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
