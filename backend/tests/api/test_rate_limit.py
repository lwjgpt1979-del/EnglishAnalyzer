"""限流（防爆破，上线硬化）tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_fixed_window_limit():
    from app.services import rate_limit_service as rl
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine)
    key = f"test:{uuid.uuid4().hex}"
    async with sf() as db:
        try:
            # limit=3：前 3 次放行，第 4 次 429
            for _ in range(3):
                await rl.hit(db, key=key, limit=3, window_seconds=300)
            with pytest.raises(AppError) as ei:
                await rl.hit(db, key=key, limit=3, window_seconds=300)
            assert ei.value.code == 429
        finally:
            async with engine.begin() as c:
                await c.execute(text("DELETE FROM rate_limits WHERE bucket_key=:k"), {"k": key})
    await engine.dispose()


def test_client_ip_xff():
    from app.services import rate_limit_service as rl

    class _Req:
        def __init__(self, xff=None, host=None):
            self.headers = {"x-forwarded-for": xff} if xff else {}
            self.client = type("C", (), {"host": host})() if host else None
    assert rl.client_ip(_Req(xff="1.2.3.4, 5.6.7.8")) == "1.2.3.4"
    assert rl.client_ip(_Req(host="9.9.9.9")) == "9.9.9.9"
    assert rl.client_ip(_Req()) == "unknown"
