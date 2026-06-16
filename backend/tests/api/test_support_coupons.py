"""客服支持体系（§13）+ 优惠券（SP-4）service-level tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "sptest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _mk_user(db, role="student"):
    uid = uuid.uuid4()
    await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,:r,true)"),
                     {"i": uid, "o": f"{_TAG}_{uid.hex[:8]}", "r": role})
    return uid


@pytest.mark.asyncio
async def test_support_faq_feedback_and_coupons():
    from app.services import (support_service, faq_service, user_feedback_service,
                              coupon_service)
    from app.models.d2_payments import Order

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    coupon_id = grant_id = None
    async with sf() as db:
        uid = await _mk_user(db)
        adm = await _mk_user(db, role="platform_admin")
        await db.flush()
        try:
            # ── 工单 §13.1 ──
            t = await support_service.create_ticket(
                db, user_id=uid, category="feature", subject="登录异常",
                content="无法登录")
            await support_service.reply(db, ticket_id=t.id, sender_role="admin",
                                        sender_id=adm, content="已为您处理")
            thread = await support_service.get_thread(db, ticket_id=t.id, user_id=uid)
            assert len(thread["messages"]) == 2 and thread["ticket"]["status"] == "replied"
            ql = await support_service.admin_list(db, status="all")
            assert any(x["id"] == str(t.id) for x in ql["items"])
            await support_service.close_ticket(db, ticket_id=t.id, admin_id=adm)

            # ── FAQ §13.2 ──
            f = await faq_service.create(db, admin_id=adm, audience="c", category="会员",
                                         question="如何续费？", answer="我的→续费")
            pub = await faq_service.public_list(db, audience="c")
            assert any(any(it["id"] == str(f.id) for it in g["items"])
                       for g in pub["categories"])
            await faq_service.update(db, faq_id=f.id, admin_id=adm, fields={"is_active": False})
            pub2 = await faq_service.public_list(db, audience="c")
            assert not any(any(it["id"] == str(f.id) for it in g["items"])
                           for g in pub2["categories"])

            # ── 意见反馈 §13.3 ──
            fb = await user_feedback_service.submit(
                db, user_id=uid, kind="bug", content="按钮点不动",
                images=["http://x/a.png"])
            await user_feedback_service.handle(db, feedback_id=fb.id, admin_id=adm,
                                               action="done", note="已修复")
            ml = await user_feedback_service.list_mine(db, user_id=uid)
            assert ml["items"][0]["status"] == "done"

            # ── 优惠券 SP-4 ──
            c = await coupon_service.admin_create(
                db, admin_id=adm, name="满100减20", discount_type="amount",
                discount_value=2000, min_amount_fen=10000, scope="all",
                with_redeem_code=True, redeem_quota=5)
            coupon_id = c.id
            assert c.redeem_code
            res = await coupon_service.redeem(db, user_id=uid, code=c.redeem_code)
            assert res["coupon"]["id"] == str(c.id)
            # 重复领取被拦
            with pytest.raises(Exception):
                await coupon_service.redeem(db, user_id=uid, code=c.redeem_code)
            # 可用券
            app_ = await coupon_service.list_applicable(db, user_id=uid, amount_fen=15000, scope="new")
            assert app_["items"] and app_["items"][0]["discount_fen"] == 2000
            grant_id = uuid.UUID(app_["items"][0]["grant_id"])
            # 金额不足 → 不可用
            app2 = await coupon_service.list_applicable(db, user_id=uid, amount_fen=5000, scope="new")
            assert not app2["items"]
            # 抵扣到订单
            order = Order(id=uuid.uuid4(), order_no=f"ORD-{_TAG}-{uuid.uuid4().hex[:8]}",
                          payer_id=uid, beneficiary_id=uid, order_type="new", tier="pro",
                          duration_months=6, amount_fen=15000, status="pending")
            db.add(order)
            await db.flush()
            d = await coupon_service.apply_to_order(db, grant_id=grant_id, user_id=uid,
                                                    order=order, scope="new")
            assert d == 2000 and order.amount_fen == 13000 and order.discount_fen == 2000
            mine_used = await coupon_service.list_mine(db, user_id=uid, status="used")
            assert mine_used["items"]
            await db.execute(text("DELETE FROM orders WHERE id=:o"), {"o": order.id})
        finally:
            await db.execute(text("DELETE FROM coupon_grants WHERE coupon_id=:c"), {"c": coupon_id} if coupon_id else {"c": uuid.uuid4()})
            if coupon_id:
                await db.execute(text("DELETE FROM coupons WHERE id=:c"), {"c": coupon_id})
            await db.execute(text("DELETE FROM support_messages WHERE ticket_id IN (SELECT id FROM support_tickets WHERE user_id=:u)"), {"u": uid})
            await db.execute(text("DELETE FROM support_tickets WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM faq_entries WHERE updated_by=:a"), {"a": adm})
            await db.execute(text("DELETE FROM user_feedback WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM notifications WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
