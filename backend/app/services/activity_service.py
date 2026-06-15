"""行为埋点（§5.5）：记录日活 + DAU/MAU/活跃趋势。

中间件每请求调用 record()，进程内按 (user_id, 日期) 去重 → 每用户每天最多一次写。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# 进程内去重缓存：{ "user_id:YYYY-MM-DD" }，避免每请求都写库
_seen: set[str] = set()


async def record(user_id: str) -> None:
    """记录该用户今日活跃（去重 + ON CONFLICT DO NOTHING，独立短事务）。"""
    today = dt.date.today().isoformat()
    key = f"{user_id}:{today}"
    if key in _seen:
        return
    _seen.add(key)
    if len(_seen) > 50000:          # 防无限增长，跨天自然失效
        _seen.clear()
        _seen.add(key)
    try:
        import uuid
        from app.core.database import _async_session_factory
        async with _async_session_factory() as s:
            await s.execute(text(
                "INSERT INTO user_activity (id, user_id, active_date) "
                "VALUES (:i, :u, :d) ON CONFLICT (user_id, active_date) DO NOTHING"),
                {"i": uuid.uuid4(), "u": user_id, "d": today})
            await s.commit()
    except Exception:           # noqa: BLE001 — 埋点失败不影响请求
        _seen.discard(key)


async def active_metrics(db: AsyncSession) -> dict:
    """DAU（今日）/ MAU（近30天去重）/ 近7天活跃趋势。"""
    from app.models.d9_system import UserActivity
    today = dt.date.today()
    d30 = today - dt.timedelta(days=29)
    d7 = today - dt.timedelta(days=6)

    dau = int(await db.scalar(
        select(func.count()).select_from(UserActivity).where(UserActivity.active_date == today)) or 0)
    mau = int(await db.scalar(
        select(func.count(func.distinct(UserActivity.user_id)))
        .where(UserActivity.active_date >= d30)) or 0)
    rows = (await db.execute(
        select(UserActivity.active_date, func.count())
        .where(UserActivity.active_date >= d7)
        .group_by(UserActivity.active_date).order_by(UserActivity.active_date))).all()
    by_date = {d.isoformat(): c for d, c in rows}
    trend = [{"date": (d7 + dt.timedelta(days=i)).isoformat(),
              "count": by_date.get((d7 + dt.timedelta(days=i)).isoformat(), 0)} for i in range(7)]
    return {"dau": dau, "mau": mau, "trend_7d": trend}
