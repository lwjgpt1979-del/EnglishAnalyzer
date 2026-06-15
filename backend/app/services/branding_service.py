"""项目品牌配置（项目名等），存 system_configs.branding，运营后台可改。

全系统唯一真源：各前端启动读 GET /config/branding，admin 改 PUT /admin/branding。
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig

_KEY = "branding"
DEFAULT_APP_NAME = "engGramer"


async def get_branding(db: AsyncSession) -> dict:
    """读品牌配置；缺失返回默认。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _KEY)
    )).scalar_one_or_none()
    data: dict = {}
    if cfg is not None:
        data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return {
        "app_name": (data.get("app_name") or DEFAULT_APP_NAME).strip() or DEFAULT_APP_NAME,
        "slogan": data.get("slogan") or "",
    }


async def set_branding(db: AsyncSession, *, app_name: str, slogan: str | None,
                       updated_by: uuid.UUID) -> dict:
    """运营改品牌：upsert system_configs.branding。"""
    name = (app_name or "").strip()
    if not name:
        from app.core.exceptions import AppError
        raise AppError(code=400, message="项目名称不能为空")
    value = {"app_name": name, "slogan": (slogan or "").strip()}
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _KEY)
    )).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_KEY, value=value,
            description="项目品牌配置（项目名/slogan）", updated_by=updated_by,
        ))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    await db.flush()
    return value
