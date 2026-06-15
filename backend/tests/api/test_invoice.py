"""发票申请记录 tests（§5.4）。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.exceptions import AppError

_TAG = "invtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_invoice_flow():
    from app.services import invoice_service as inv

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid, aid = uuid.uuid4(), uuid.uuid4()
        oid = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
        await db.execute(text(
            "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,duration_months,amount_fen,status) "
            "VALUES (:i,:no,:u,:u,'new','pro',6,10000,'paid')"),
            {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "u": uid})
        await db.flush()
        try:
            # 1) 企业抬头缺税号 → 400
            with pytest.raises(AppError):
                await inv.request_invoice(db, user_id=uid, order_id=oid,
                    title_type="company", title="某公司", tax_no=None, content=None, email=None)
            # 2) 正常申请
            rec = await inv.request_invoice(db, user_id=uid, order_id=oid,
                title_type="company", title="某科技公司", tax_no="91310000XXXX",
                content="会员服务费", email="a@b.com")
            assert rec.status == "pending" and rec.amount_fen == 10000
            # 3) 重复申请 → 400
            with pytest.raises(AppError):
                await inv.request_invoice(db, user_id=uid, order_id=oid,
                    title_type="personal", title="个人", tax_no=None, content=None, email=None)
            # 4) 我的列表
            mine = await inv.list_mine(db, user_id=uid)
            assert len(mine) == 1 and mine[0]["title"] == "某科技公司"
            # 5) 后台开具
            done = await inv.issue(db, invoice_id=rec.id, admin_id=aid,
                                   invoice_no="INV-0001", invoice_url="http://x/inv.pdf")
            assert done.status == "issued" and done.invoice_no == "INV-0001"
            # 6) 开具后可重新申请(因无 pending/issued 拦截?) → 已 issued 仍拦截
            with pytest.raises(AppError):
                await inv.request_invoice(db, user_id=uid, order_id=oid,
                    title_type="personal", title="个人", tax_no=None, content=None, email=None)
            # 7) 后台列表
            lst = await inv.admin_list(db, status="issued")
            assert any(i["id"] == str(rec.id) for i in lst["items"])
        finally:
            await db.execute(text("DELETE FROM invoice_requests WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM orders WHERE order_no LIKE :p"), {"p": f"ORD-{_TAG}-%"})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
