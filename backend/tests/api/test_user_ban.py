"""用户封禁/解封 + 临时到期自动解封 tests（§5.3.1）。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.exceptions import AppError

_TAG = "bantest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _mk_user(db, role="student"):
    uid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,:r,true)"),
        {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}", "r": role})
    return uid


@pytest.mark.asyncio
async def test_ban_unban_and_auto_expire():
    from app.services import user_admin_service as svc
    from app.models.d1_users import User

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            # 1) 永久封禁(无 days)
            uid = await _mk_user(db)
            await db.flush()
            u = await svc.ban_user(db, user_id=uid, reason="伪造支付截图", days=None)
            assert u.is_active is False and u.banned_until is None
            item = svc._to_item(u)
            assert item["ban_type"] == "permanent" and item["banned"] is True

            # 2) 原因必填
            uid2 = await _mk_user(db)
            await db.flush()
            with pytest.raises(AppError):
                await svc.ban_user(db, user_id=uid2, reason="  ", days=None)

            # 3) 不能封管理员
            aid = await _mk_user(db, role="platform_admin")
            await db.flush()
            with pytest.raises(AppError):
                await svc.ban_user(db, user_id=aid, reason="x", days=7)

            # 4) 临时封禁 7 天
            u4 = await _mk_user(db)
            await db.flush()
            r = await svc.ban_user(db, user_id=u4, reason="异常多设备", days=7)
            assert r.is_active is False and r.banned_until is not None
            assert svc._to_item(r)["ban_type"] == "temporary"

            # 5) 解封
            await svc.unban_user(db, user_id=u4)
            uu = await db.get(User, u4)
            assert uu.is_active is True and uu.ban_reason is None and uu.banned_until is None

            # 6) 搜索能查到
            res = await svc.list_users(db, q=_TAG, limit=200)
            # 搜索按 nickname/phone/id，这里 nickname/phone 为空，用 id 精确查
            one = await svc.list_users(db, q=str(uid))
            assert one["total"] >= 1 and any(i["id"] == str(uid) for i in one["items"])
        finally:
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_membership_pause_on_unban():
    """解封时会员有效期顺延封禁时长。"""
    from app.services import user_admin_service as svc
    import datetime as dt
    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = await _mk_user(db)
        now = dt.datetime.now(dt.timezone.utc)
        exp0 = now + dt.timedelta(days=10)
        await db.execute(text(
            "INSERT INTO memberships (id,user_id,tier,started_at,expires_at,is_active) "
            "VALUES (:i,:u,'pro',:s,:e,true)"),
            {"i": uuid.uuid4(), "u": uid, "s": now, "e": exp0})
        await db.flush()
        try:
            # 封禁(banned_at 设为 3 天前模拟已封禁 3 天)
            from app.models.d1_users import User
            await svc.ban_user(db, user_id=uid, reason="测试", days=30)
            u = await db.get(User, uid)
            u.banned_at = now - dt.timedelta(days=3)
            await db.flush()
            # 解封 → 会员顺延约 3 天
            await svc.unban_user(db, user_id=uid)
            from app.models.d2_payments import Membership
            mem = await db.scalar(text("SELECT expires_at FROM memberships WHERE user_id=:u").bindparams(u=uid))
            # 顺延后应 > 原到期 + 2.9 天
            assert mem >= exp0 + dt.timedelta(days=2, hours=23)
        finally:
            await db.execute(text("DELETE FROM memberships WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await db.commit()
    await engine.dispose()
