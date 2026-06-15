"""退款异步对账 handle_refund_notify tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "refundnotify"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _mk_order_and_refund(db, out_refund_no, status="pending"):
    uid = uuid.uuid4()
    oid = uuid.uuid4()
    rid = uuid.uuid4()
    await db.execute(text("INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
                     {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    await db.execute(text(
        "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,duration_months,amount_fen,status) "
        "VALUES (:i,:no,:u,:u,'new','pro',6,10000,'refunded')"),
        {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "u": uid})
    await db.execute(text(
        "INSERT INTO refund_records (id,order_id,amount_fen,refund_type,status,out_refund_no) "
        "VALUES (:i,:oid,10000,'standard_7d',:st,:orn)"),
        {"i": rid, "oid": oid, "st": status, "orn": out_refund_no})
    await db.flush()
    return uid, rid


async def _cleanup(db):
    await db.execute(text(
        "DELETE FROM refund_records WHERE order_id IN (SELECT id FROM orders WHERE order_no LIKE :p)"),
        {"p": f"ORD-{_TAG}-%"})
    await db.execute(text("DELETE FROM orders WHERE order_no LIKE :p"), {"p": f"ORD-{_TAG}-%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_refund_notify_reconcile():
    from app.services import refund_service as rs
    from app.models.d2_payments import RefundRecord

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            orn = f"RF{_TAG}{uuid.uuid4().hex[:10]}"
            _, rid = await _mk_order_and_refund(db, orn, status="pending")

            # 1) SUCCESS → completed + 记录原始状态 + 回填 refund_id
            res = await rs.handle_refund_notify(db, {
                "out_refund_no": orn, "refund_id": "wx_refund_xyz", "refund_status": "SUCCESS"})
            assert res["matched"] is True
            rec = await db.get(RefundRecord, rid)
            assert rec.status == "completed" and rec.wx_refund_status == "SUCCESS"
            assert rec.wx_refund_id == "wx_refund_xyz"

            # 2) 未匹配的 out_refund_no
            res2 = await rs.handle_refund_notify(db, {"out_refund_no": "RF_not_exist", "refund_status": "SUCCESS"})
            assert res2["matched"] is False

            # 3) ABNORMAL → 标记异常
            orn2 = f"RF{_TAG}{uuid.uuid4().hex[:10]}"
            _, rid2 = await _mk_order_and_refund(db, orn2, status="pending")
            await rs.handle_refund_notify(db, {"out_refund_no": orn2, "refund_status": "ABNORMAL"})
            rec2 = await db.get(RefundRecord, rid2)
            assert rec2.wx_refund_status == "ABNORMAL" and rec2.state_code == "REFUND_ABNORMAL"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
