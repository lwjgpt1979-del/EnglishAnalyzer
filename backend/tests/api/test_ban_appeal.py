"""封禁申诉闭环 tests（§5.3.1）。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.exceptions import AppError

_TAG = "appealtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_ban_appeal_flow():
    from app.services import ban_appeal_service as svc, user_admin_service as uas
    from app.models.d1_users import User

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = uuid.uuid4()
        aid = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
        await db.flush()
        try:
            user = await db.get(User, uid)
            # 1) 未封禁不能申诉
            with pytest.raises(AppError):
                await svc.submit(db, user=user, reason="x", evidence_urls=None)
            # 2) 封禁后申诉
            await uas.ban_user(db, user_id=uid, reason="误判测试", days=7)
            user = await db.get(User, uid)
            rec = await svc.submit(db, user=user, reason="我没有违规", evidence_urls=["http://x/a.jpg"])
            assert rec.status == "pending"
            # 3) 重复 pending → 拒
            with pytest.raises(AppError):
                await svc.submit(db, user=user, reason="再申诉", evidence_urls=None)
            # 4) 后台列表
            lst = await svc.admin_list(db, status="pending")
            assert any(i["id"] == str(rec.id) for i in lst["items"])
            # 5) 审核通过 → 解封
            await svc.review(db, appeal_id=rec.id, admin_id=aid, approve=True, note="误判已解封")
            u2 = await db.get(User, uid)
            assert u2.is_active is True and u2.ban_reason is None
            # 6) 已处理不可再审
            with pytest.raises(AppError):
                await svc.review(db, appeal_id=rec.id, admin_id=aid, approve=False, note="x")
        finally:
            await db.execute(text("DELETE FROM ban_appeals WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await db.commit()
    await engine.dispose()
