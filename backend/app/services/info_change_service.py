"""学习信息变更月度上限（§5.6）。

学生每自然月可修改 年级/教材版本/学期 的总次数上限（防滥用，默认 3 次/月）。
全局上限存 system_configs.info_change_limit（后台可改，调整次月起生效——计数按自然月桶天然重置）。
计数复用 feature_usage（key=profile.info_change，月桶），不新建表。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SystemConfig

KEY = "profile.info_change"
SYS_KEY = "info_change_limit"
DEFAULT_LIMIT = 3


async def get_limit(db: AsyncSession) -> int:
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == SYS_KEY))).scalar_one_or_none()
    if cfg is None:
        return DEFAULT_LIMIT
    try:
        v = cfg.value if isinstance(cfg.value, int) else (cfg.value or {}).get("value")
        return int(v) if v is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


async def set_limit(db: AsyncSession, *, value: int, admin_id: uuid.UUID) -> int:
    if value < 0:
        raise AppError(code=400, message="次数上限不能为负")
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == SYS_KEY))).scalar_one_or_none()
    payload = {"value": int(value)}
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=SYS_KEY, value=payload,
                            description="学习信息（年级/教材/学期）变更月度上限（§5.6）",
                            updated_by=admin_id))
    else:
        cfg.value = payload
        cfg.updated_by = admin_id
    await db.flush()
    return int(value)


async def _used_this_month(db: AsyncSession, user_id: uuid.UUID) -> int:
    from app.services import entitlement_service as es
    return await es._usage_count(db, user_id=user_id, key=KEY, period="month")


async def usage(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    limit = await get_limit(db)
    used = await _used_this_month(db, user_id)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


async def assert_and_consume(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    """变更前校验本月次数；未超则计一次。与业务同事务（调用方 commit）。"""
    from app.services import entitlement_service as es
    limit = await get_limit(db)
    used = await _used_this_month(db, user_id)
    if used >= limit:
        raise AppError(code=403,
                       message=f"本月学习信息修改已达上限（{limit} 次），下月 1 日恢复")
    await db.execute(es.pg_insert_usage(user_id, KEY, es._bucket("month")))
