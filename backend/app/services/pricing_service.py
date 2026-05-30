"""V2 学期定价（从 system_configs 读，运营可改 SQL）。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.schemas.semesters import SemesterPricing

DEFAULT_PRICING = SemesterPricing(basic=39, pro=79, promax=159)


async def get_semester_pricing(db: AsyncSession) -> SemesterPricing:
    """读 system_configs.semester_pricing。缺失则返回默认值。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == "semester_pricing"))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return DEFAULT_PRICING
    data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return SemesterPricing(**data)


def calc_total_fen(
    pricing: SemesterPricing, *, tier: str, semester_count: int,
) -> int:
    """计算总金额（分）。tier×单价×学期数。"""
    unit_yuan = {"basic": pricing.basic, "pro": pricing.pro, "promax": pricing.promax}[tier]
    return unit_yuan * semester_count * 100
