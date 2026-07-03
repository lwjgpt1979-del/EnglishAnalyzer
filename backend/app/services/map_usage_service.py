"""地图获客「每日查询次数」限额 + 用量统计(百度/高德共用)。

运营可配每日上限(system_configs.map_fetch.daily_quota),按东八区自然日计数;
采集时每发一次地图 API 就 bump 一次,到上限即停(自我保护,别撞爆第三方配额)。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig

_KEY = "map_fetch"
_CN_TZ = timezone(timedelta(hours=8))
SOURCES = ("baidu", "amap")

DEFAULTS: dict = {
    "daily_quota": {"baidu": 100, "amap": 100},   # 每日查询次数上限(可运营配置)
}


def _today() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


async def _row(db: AsyncSession) -> SystemConfig | None:
    return (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()


async def get_config(db: AsyncSession) -> dict:
    row = await _row(db)
    quota = dict(DEFAULTS["daily_quota"])
    if row is not None and isinstance(row.value, dict):
        quota.update(row.value.get("daily_quota") or {})
    return {"daily_quota": {s: int(quota.get(s, DEFAULTS["daily_quota"][s])) for s in SOURCES}}


async def _usage_today(db: AsyncSession) -> dict:
    """今日用量(跨天自动归零)。返回 {baidu:int, amap:int}。"""
    row = await _row(db)
    u = (row.value.get("usage") if row is not None and isinstance(row.value, dict) else None) or {}
    if u.get("date") != _today():
        return {s: 0 for s in SOURCES}
    return {s: int(u.get(s, 0)) for s in SOURCES}


async def get_usage(db: AsyncSession) -> dict:
    """{baidu:{used,quota,remaining}, amap:{...}, date}。"""
    cfg = await get_config(db)
    used = await _usage_today(db)
    out = {"date": _today()}
    for s in SOURCES:
        q = cfg["daily_quota"][s]
        out[s] = {"used": used[s], "quota": q, "remaining": max(0, q - used[s])}
    return out


async def remaining(db: AsyncSession, source: str) -> int:
    cfg = await get_config(db)
    used = await _usage_today(db)
    q = cfg["daily_quota"].get(source, 0)
    return max(0, q - used.get(source, 0))


async def bump(db: AsyncSession, *, source: str, n: int) -> None:
    """把今日 source 用量 +n(跨天先归零)。随调用方事务落库。"""
    if n <= 0 or source not in SOURCES:
        return
    row = await _row(db)
    today = _today()
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY,
                            value={"daily_quota": dict(DEFAULTS["daily_quota"]),
                                   "usage": {"date": today, source: n}},
                            description="地图获客每日限额 + 用量"))
        await db.flush()
        return
    val = dict(row.value or {})
    u = dict(val.get("usage") or {})
    if u.get("date") != today:
        u = {"date": today}
    u[source] = int(u.get(source, 0)) + n
    val["usage"] = u
    row.value = val
    await db.flush()


async def set_quota(db: AsyncSession, *, quota: dict, updated_by: uuid.UUID) -> dict:
    """设置每日上限。quota={baidu?:int, amap?:int}。"""
    clean = {s: int(quota[s]) for s in SOURCES if s in quota and quota[s] is not None}
    row = await _row(db)
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY,
                            value={"daily_quota": {**DEFAULTS["daily_quota"], **clean}},
                            description="地图获客每日限额 + 用量", updated_by=updated_by))
    else:
        val = dict(row.value or {})
        val["daily_quota"] = {**DEFAULTS["daily_quota"], **(val.get("daily_quota") or {}), **clean}
        row.value = val
        row.updated_by = updated_by
    await db.flush()
    return await get_config(db)
