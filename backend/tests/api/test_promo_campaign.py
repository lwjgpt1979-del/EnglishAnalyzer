"""限时活动价 campaign（§5.7）tests。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "promotest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_campaign_pricing_and_order_and_once_limit():
    from app.services import promo_service, order_service

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm = uuid.uuid4()
        payer = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_adm_{adm.hex[:8]}"})
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": payer, "o": f"{_TAG}_{payer.hex[:8]}"})
        await db.flush()
        now = dt.datetime.now(dt.timezone.utc)
        cid = None
        try:
            c = await promo_service.admin_create(
                db, admin_id=adm, name=f"{_TAG} 开学季",
                starts_at=now - dt.timedelta(hours=1), ends_at=now + dt.timedelta(days=3),
                price_pro=50, limit_type="once", is_promotional=True)
            cid = c.id
            await db.flush()

            # 生效定价：pro 实售=50，划线价=原价
            eff = await promo_service.effective_semester_pricing(db)
            assert eff["pro"] == 50 and eff["list_pro"] > 0
            assert eff["campaign"] and eff["campaign"]["name"].endswith("开学季")

            # 下单走活动价
            sem = [{"textbook_version": "RJ", "grade": "G7", "semester": "上"}]
            order = await order_service.create_order(
                db, payer_id=payer, beneficiary_id=payer, tier="pro",
                order_type="new", semesters=sem)
            assert order.amount_fen == 5000          # 50 元 ×1 学期
            assert order.is_promotional is True
            assert str(order.promo_campaign_id) == str(cid)
            await db.refresh(c)
            assert c.sold_count == 1

            # once 限购：同一 payer 再下单 → 报错
            with pytest.raises(Exception):
                await order_service.create_order(
                    db, payer_id=payer, beneficiary_id=payer, tier="pro",
                    order_type="new", semesters=sem)

            # 停用活动后恢复原价
            await promo_service.admin_set_active(db, campaign_id=cid, is_active=False)
            eff2 = await promo_service.effective_semester_pricing(db)
            assert eff2["campaign"] is None
        finally:
            await db.execute(text("DELETE FROM orders WHERE payer_id=:p"), {"p": payer})
            if cid:
                await db.execute(text("DELETE FROM promo_campaigns WHERE id=:c"), {"c": cid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
