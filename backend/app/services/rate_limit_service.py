"""固定窗口限流（防爆破，上线硬化）。

DB 计数，跨 worker 正确：INSERT ... ON CONFLICT DO UPDATE count=count+1 原子自增。
用独立短事务自增，避免与调用方业务事务耦合 / 被回滚。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError


def client_ip(request) -> str:
    """取客户端 IP：优先 X-Forwarded-For 首段（经 nginx），回落 request.client。"""
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()[:45]
    try:
        return (request.client.host if request and request.client else "unknown")[:45]
    except Exception:
        return "unknown"


def _window_start(window_seconds: int, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    epoch = int(now.timestamp())
    aligned = epoch - (epoch % window_seconds)
    return dt.datetime.fromtimestamp(aligned, tz=dt.timezone.utc)


async def hit(db: AsyncSession, *, key: str, limit: int, window_seconds: int,
              message: str = "操作过于频繁，请稍后再试") -> None:
    """对 key 计一次数；超过 limit/窗口 → 抛 AppError(429)。

    使用 ON CONFLICT 原子自增并取回当前计数；用嵌套连接的独立提交避免污染业务事务。
    """
    ws = _window_start(window_seconds)
    # 独立事务自增（即使后续业务回滚，限流计数仍生效，防绕过；用应用 async 引擎）
    from app.core.database import _async_engine
    async with _async_engine.connect() as conn:
        cnt = await conn.scalar(text(
            "INSERT INTO rate_limits (id, bucket_key, window_start, count) "
            "VALUES (gen_random_uuid(), :k, :w, 1) "
            "ON CONFLICT (bucket_key, window_start) "
            "DO UPDATE SET count = rate_limits.count + 1 "
            "RETURNING count"), {"k": key[:160], "w": ws})
        await conn.commit()
    if cnt is not None and int(cnt) > limit:
        raise AppError(code=429, message=message)


async def cleanup(db: AsyncSession, *, older_than_hours: int = 24) -> int:
    """清理过期窗口行（cron 可选）。"""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=older_than_hours)
    res = await db.execute(text("DELETE FROM rate_limits WHERE window_start < :c"), {"c": cutoff})
    await db.commit()
    return res.rowcount or 0
