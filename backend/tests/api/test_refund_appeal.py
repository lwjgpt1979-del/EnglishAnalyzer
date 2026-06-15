"""退款 / 申诉规则引擎 tests（§4.5 决策树全分支）。

自包含造数据（唯一前缀）+ finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.exceptions import AppError

_TAG = "refundtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _mk_user(db, active=True):
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',:a)"),
        {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}", "a": active},
    )
    return uid


async def _mk_order(db, uid, *, paid_days_ago=3, amount=10000, tier="pro",
                    total_days=180, status="paid", promotional=False, created_at=None):
    oid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    paid = now - timedelta(days=paid_days_ago)
    created = created_at or paid
    await db.execute(text(
        "INSERT INTO orders (id,order_no,payer_id,beneficiary_id,order_type,tier,"
        "duration_months,amount_fen,status,paid_at,total_days,is_promotional,created_at) "
        "VALUES (:i,:no,:p,:b,'new',:t,6,:amt,:st,:pa,:td,:promo,:ca)"),
        {"i": oid, "no": f"ORD-{_TAG}-{oid.hex[:8]}", "p": uid, "b": uid, "t": tier,
         "amt": amount, "st": status, "pa": paid, "td": total_days,
         "promo": promotional, "ca": created})
    return oid


async def _mark_used(db, uid):
    """造一条 feature_usage 让 _used_since>0。"""
    await db.execute(text(
        "INSERT INTO feature_usage (id,user_id,feature_key,period_bucket,count,updated_at) "
        "VALUES (:i,:u,'vocab.shadow','2026-W24',1,now())"),
        {"i": uuid.uuid4(), "u": uid})


async def _load_order(db, oid):
    from app.models.d2_payments import Order
    return await db.get(Order, oid)


async def _load_user(db, uid):
    from app.models.d1_users import User
    return await db.get(User, uid)


async def _cleanup(db):
    usr = "(SELECT id FROM users WHERE openid LIKE :p)"
    await db.execute(text(
        f"DELETE FROM refund_records WHERE order_id IN "
        f"(SELECT id FROM orders WHERE payer_id IN {usr} OR beneficiary_id IN {usr})"),
        {"p": f"{_TAG}_%"})
    await db.execute(text(
        f"DELETE FROM orders WHERE payer_id IN {usr} OR beneficiary_id IN {usr}"),
        {"p": f"{_TAG}_%"})
    for tbl in ("feature_usage", "daily_usage", "payment_confirm_logs"):
        await db.execute(text(f"DELETE FROM {tbl} WHERE user_id IN {usr}"),
                         {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_refund_and_appeal_decision_tree():
    from app.services import refund_service as rs, order_service

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            # 1) 封禁 → REJECT_BANNED
            u_ban = await _mk_user(db, active=False)
            o_ban = await _mk_order(db, u_ban)
            await db.flush()
            with pytest.raises(AppError):
                await rs.request_refund(db, await _load_user(db, u_ban), o_ban)
            assert (await _load_order(db, o_ban)).refund_status == "REJECT_BANNED"

            # 2) 活动价 → REJECT_PROMOTIONAL
            u = await _mk_user(db)
            o_promo = await _mk_order(db, u, promotional=True)
            await db.flush()
            with pytest.raises(AppError):
                await rs.request_refund(db, await _load_user(db, u), o_promo)
            assert (await _load_order(db, o_promo)).refund_status == "REJECT_PROMOTIONAL"

            # 3) 7天内未使用 → AUTO_FULL_REFUND
            u3 = await _mk_user(db)
            o3 = await _mk_order(db, u3, paid_days_ago=3, amount=10000)
            await db.flush()
            rec = await rs.request_refund(db, await _load_user(db, u3), o3)
            assert rec.state_code == "AUTO_FULL_REFUND"
            assert rec.status == "completed" and rec.amount_fen == 10000
            assert rec.wx_refund_id and rec.wx_refund_id.startswith("mock_refund_")
            ord3 = await _load_order(db, o3)
            assert ord3.status == "refunded" and ord3.refund_status == "AUTO_FULL_REFUND"

            # 4) 7天内已使用 → MANUAL_REVIEW_PARTIAL（按比例）
            u4 = await _mk_user(db)
            o4 = await _mk_order(db, u4, paid_days_ago=3, amount=10000, total_days=180)
            await _mark_used(db, u4)
            await db.flush()
            rec4 = await rs.request_refund(db, await _load_user(db, u4), o4)
            # used = 3天前购买，含当天 = 4；remaining=176；10000*176//180
            assert rec4.state_code == "MANUAL_REVIEW_PARTIAL"
            assert rec4.status == "pending" and rec4.refund_type == "prorated"
            assert rec4.amount_fen == (10000 * (180 - 4)) // 180
            assert (await _load_order(db, o4)).refund_status == "MANUAL_REVIEW_PARTIAL"

            # 5) 超7天无申诉 → 拒
            u5 = await _mk_user(db)
            o5 = await _mk_order(db, u5, paid_days_ago=10)
            await db.flush()
            with pytest.raises(AppError):
                await rs.request_refund(db, await _load_user(db, u5), o5)
            assert (await _load_order(db, o5)).refund_status == "REJECT_OVERTIME"

            # 6) 重复购买 → AUTO_DUPLICATE_REFUND
            u6 = await _mk_user(db)
            now = datetime.now(timezone.utc)
            # 较早一单（保留），与重复单同档位、72h 内
            await _mk_order(db, u6, paid_days_ago=10, tier="pro",
                            created_at=now - timedelta(hours=2))
            o6b = await _mk_order(db, u6, paid_days_ago=10, tier="pro",
                                  amount=10000, created_at=now - timedelta(hours=1))
            await db.flush()
            rec6 = await rs.submit_appeal(db, await _load_user(db, u6), o6b,
                                          appeal_type="DUPLICATE_PURCHASE",
                                          note="重复下单", evidence_urls=None)
            assert rec6.state_code == "AUTO_DUPLICATE_REFUND"
            assert rec6.status == "completed" and rec6.amount_fen == 10000
            assert (await _load_order(db, o6b)).appeal_status == "AUTO_DUPLICATE_REFUND"

            # 7) 年度申诉配额用尽 → 拒
            u7 = await _mk_user(db)
            o7 = await _mk_order(db, u7, paid_days_ago=10, tier="basic")
            # 预置当年已申诉 1 次
            await db.execute(text(
                "INSERT INTO daily_usage (id,user_id,usage_type,period,count) "
                "VALUES (:i,:u,'appeal_annual',:p,1)"),
                {"i": uuid.uuid4(), "u": u7,
                 "p": datetime(now.year, 1, 1).date()})
            await db.flush()
            with pytest.raises(AppError):
                await rs.submit_appeal(db, await _load_user(db, u7), o7,
                                       appeal_type="DESC_MISMATCH",
                                       note="不符", evidence_urls=None)

            # 8) 非重复类申诉 → MANUAL_REVIEW_APPEAL + 消耗年度配额
            u8 = await _mk_user(db)
            o8 = await _mk_order(db, u8, paid_days_ago=10)
            await db.flush()
            rec8 = await rs.submit_appeal(db, await _load_user(db, u8), o8,
                                          appeal_type="DESC_MISMATCH",
                                          note="描述不符", evidence_urls=["http://x/a.jpg"])
            assert rec8.state_code == "MANUAL_REVIEW_APPEAL" and rec8.status == "pending"
            cnt = await db.scalar(text(
                "SELECT count FROM daily_usage WHERE user_id=:u AND usage_type='appeal_annual'"),
                {"u": u8})
            assert cnt == 1

            # 9) create_order 落 total_days / is_promotional / 关联 confirm log
            u9 = await _mk_user(db)
            log_id = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO payment_confirm_logs "
                "(id,user_id,checkbox_refund_policy,checkbox_digital_service) "
                "VALUES (:i,:u,true,true)"), {"i": log_id, "u": u9})
            await db.flush()
            o9 = await order_service.create_order(
                db, payer_id=u9, beneficiary_id=u9, tier="pro",
                quantity=1, order_type="new", is_promotional=True,
                payment_confirm_log_id=log_id)
            assert o9.total_days == 180 and o9.is_promotional is True
            assert o9.payment_confirm_log_id == log_id

            # 10) 后台审核：人工按比例退款 approve → completed + REFUND_PARTIAL_APPROVED
            admin_id = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO users (id,openid,role,is_active) "
                "VALUES (:i,:o,'platform_admin',true)"),
                {"i": admin_id, "o": f"{_TAG}_admin"})
            u10 = await _mk_user(db)
            o10 = await _mk_order(db, u10, paid_days_ago=3, amount=10000, total_days=180)
            await _mark_used(db, u10)
            await db.flush()
            rec10 = await rs.request_refund(db, await _load_user(db, u10), o10)
            assert rec10.status == "pending"
            admin = await _load_user(db, admin_id)
            done = await rs.review(db, admin, rec10.id, approve=True, amount_fen=5000)
            assert done.status == "completed" and done.amount_fen == 5000
            assert done.state_code == "REFUND_PARTIAL_APPROVED"
            assert (await _load_order(db, o10)).refund_status == "REFUND_PARTIAL_APPROVED"
            assert done.reviewed_by == admin_id

            # 11) list_reviews + 二次审核拦截
            lst = await rs.list_reviews(db, kind="all", status="all", limit=200)
            assert lst["total"] >= 1
            with pytest.raises(AppError):
                await rs.review(db, admin, rec10.id, approve=True)  # 已处理

            # 12) 举证包
            pack = await rs.evidence_pack(db, o10)
            assert pack["order"]["order_no"].startswith(f"ORD-{_TAG}-")
            assert pack["usage_count_since_paid"] >= 1
            assert len(pack["refund_records"]) >= 1
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
