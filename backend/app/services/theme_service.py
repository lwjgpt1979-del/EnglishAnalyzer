"""主题选择 service（M11）：active 主题 key 存 system_configs。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.themes import DEFAULT_THEME_KEY, THEMES, get_theme
from app.models.d9_system import SystemConfig

_KEY = "active_theme"


async def get_active_key(db: AsyncSession) -> str:
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return DEFAULT_THEME_KEY
    val = cfg.value
    if isinstance(val, dict):
        return val.get("key", DEFAULT_THEME_KEY)
    return str(val) if val else DEFAULT_THEME_KEY


async def get_active_theme(db: AsyncSession) -> dict:
    return get_theme(await get_active_key(db))


async def list_themes(db: AsyncSession) -> dict:
    return {"active_key": await get_active_key(db), "themes": THEMES}


async def set_active(db: AsyncSession, *, key: str, operator_id: uuid.UUID) -> dict:
    theme = get_theme(key)  # 校验：不存在则回退默认（不报错，保证幂等）
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_KEY, value={"key": theme["key"]},
            description="小程序上线主题 key", updated_by=operator_id,
        ))
    else:
        cfg.value = {"key": theme["key"]}
        cfg.updated_by = operator_id
    await db.flush()
    return theme
