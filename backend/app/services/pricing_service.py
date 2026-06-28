"""V2 学期定价（从 system_configs 读，运营可改 SQL）。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig, PriceChangeLog
from app.schemas.institution import InstitutionCodePricing
from app.schemas.semesters import SemesterPricing

DEFAULT_PRICING = SemesterPricing(basic=39, pro=79, promax=159)

_PRICING_KEY = "semester_pricing"

# 机构激活码定价（分 / 月）。默认值即历史写死常量，运营后台可改。
DEFAULT_INSTITUTION_CODE_PRICING = InstitutionCodePricing(basic=1500, pro=3000, promax=5000)

_INSTITUTION_CODE_PRICING_KEY = "institution_code_pricing"


async def get_semester_pricing(db: AsyncSession) -> SemesterPricing:
    """读 system_configs.semester_pricing。缺失则返回默认值。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _PRICING_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return DEFAULT_PRICING
    data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return SemesterPricing(**data)


async def update_semester_pricing(
    db: AsyncSession,
    *,
    pricing: SemesterPricing,
    updated_by: uuid.UUID,
) -> SemesterPricing:
    """运营改学期定价：upsert system_configs.semester_pricing（key 唯一）。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _PRICING_KEY)
    )).scalar_one_or_none()
    value = pricing.model_dump()
    if cfg is None:
        db.add(SystemConfig(
            id=uuid.uuid4(),
            key=_PRICING_KEY,
            value=value,
            description="V2 学期会员定价（basic/pro/promax 元/学期）",
            updated_by=updated_by,
        ))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    # §5.7 历史价格存档：每次变更存快照，用于退款/争议举证
    db.add(PriceChangeLog(
        id=uuid.uuid4(), config_key=_PRICING_KEY, snapshot=value, changed_by=updated_by))
    await db.flush()
    return pricing


async def pricing_history(db: AsyncSession, *, limit: int = 50) -> list[dict]:
    """定价变更历史（倒序）。"""
    rows = (await db.execute(
        select(PriceChangeLog).where(PriceChangeLog.config_key == _PRICING_KEY)
        .order_by(PriceChangeLog.created_at.desc()).limit(limit))).scalars().all()
    return [
        {"id": str(r.id), "snapshot": r.snapshot,
         "changed_by": str(r.changed_by) if r.changed_by else None,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


def calc_total_fen(
    pricing: SemesterPricing, *, tier: str, semester_count: int,
) -> int:
    """计算总金额（分）。tier×单价×学期数。"""
    unit_yuan = {"basic": pricing.basic, "pro": pricing.pro, "promax": pricing.promax}[tier]
    return unit_yuan * semester_count * 100


# ─── 机构激活码定价（分 / 月）──────────────────────────────────────────────

async def get_institution_code_pricing(db: AsyncSession) -> InstitutionCodePricing:
    """读 system_configs.institution_code_pricing（分 / 月）。缺失则返回默认兜底。"""
    r = await db.execute(
        select(SystemConfig).where(SystemConfig.key == _INSTITUTION_CODE_PRICING_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return DEFAULT_INSTITUTION_CODE_PRICING
    data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return InstitutionCodePricing(**data)


async def update_institution_code_pricing(
    db: AsyncSession,
    *,
    pricing: InstitutionCodePricing,
    updated_by: uuid.UUID,
) -> InstitutionCodePricing:
    """运营改机构激活码定价：upsert system_configs.institution_code_pricing（key 唯一）。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _INSTITUTION_CODE_PRICING_KEY)
    )).scalar_one_or_none()
    value = pricing.model_dump()
    if cfg is None:
        db.add(SystemConfig(
            id=uuid.uuid4(),
            key=_INSTITUTION_CODE_PRICING_KEY,
            value=value,
            description="机构激活码档位定价（basic/pro/promax 分 / 月）",
            updated_by=updated_by,
        ))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    # 历史价格存档：每次变更存快照，用于退款/争议举证
    db.add(PriceChangeLog(
        id=uuid.uuid4(), config_key=_INSTITUTION_CODE_PRICING_KEY,
        snapshot=value, changed_by=updated_by))
    await db.flush()
    return pricing


async def institution_code_pricing_history(
    db: AsyncSession, *, limit: int = 50
) -> list[dict]:
    """机构激活码定价变更历史（倒序）。"""
    rows = (await db.execute(
        select(PriceChangeLog)
        .where(PriceChangeLog.config_key == _INSTITUTION_CODE_PRICING_KEY)
        .order_by(PriceChangeLog.created_at.desc()).limit(limit))).scalars().all()
    return [
        {"id": str(r.id), "snapshot": r.snapshot,
         "changed_by": str(r.changed_by) if r.changed_by else None,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
