"""学习信息变更月度上限（§5.6）tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "icl"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_info_change_limit_and_config():
    from app.services import info_change_service as ic
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm, stu = uuid.uuid4(), uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_adm_{adm.hex[:6]}"})
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": stu, "o": f"{_TAG}_{stu.hex[:6]}"})
        await db.flush()
        try:
            # 默认 3
            assert await ic.get_limit(db) == 3
            # 改为 2
            await ic.set_limit(db, value=2, admin_id=adm)
            assert await ic.get_limit(db) == 2

            u0 = await ic.usage(db, user_id=stu)
            assert u0 == {"used": 0, "limit": 2, "remaining": 2}

            # 消费 2 次
            await ic.assert_and_consume(db, user_id=stu)
            await ic.assert_and_consume(db, user_id=stu)
            u2 = await ic.usage(db, user_id=stu)
            assert u2["used"] == 2 and u2["remaining"] == 0
            # 第 3 次被拦
            with pytest.raises(AppError) as ei:
                await ic.assert_and_consume(db, user_id=stu)
            assert ei.value.code == 403
        finally:
            await db.execute(text("DELETE FROM feature_usage WHERE user_id=:u"), {"u": stu})
            await db.execute(text("DELETE FROM system_configs WHERE key='info_change_limit'"))
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
