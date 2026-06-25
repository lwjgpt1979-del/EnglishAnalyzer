"""R10.8 语法掌握/定级参数配置(运营可改,走 system_configs)。

遵守 CLAUDE.md 铁律:阈值/权重等运营可调值经此 service 从 system_configs 读取,
代码里的 DEFAULTS 仅作"配置缺失时的兜底",不决定实际行为(改后台即生效)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig

_KEY = "grammar_config"

DEFAULTS: dict = {
    # 掌握门槛(各维 BKT 达阈)
    "detect_mastered": 0.85,
    "produce_mastered": 0.85,
    "recognize_mastered": 0.85,
    # 间隔复测
    "retain_min_days": 3,
    "retain_ladder": [3, 7, 15, 30, 60],
    # 分级测验
    "placement_max_items": 25,
    "prior_asked_ok": 0.70,
    "prior_asked_no": 0.10,
    "prior_infer_ok": 0.55,
    "prior_infer_no": 0.15,
    # 纸质先验
    "paper_half_life_days": 90,
    "paper_mastered_discount": 0.30,
}

_CACHE: dict = dict(DEFAULTS)


async def get_config(db: AsyncSession) -> dict:
    """读取配置(合并默认),并刷新进程内缓存。"""
    global _CACHE
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    cfg = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        cfg.update({k: v for k, v in row.value.items() if k in DEFAULTS})
    _CACHE = cfg
    return cfg


def cached() -> dict:
    """同步取最近一次加载的配置(供 _axes_mastered 等同步逻辑用;未加载则返回默认)。"""
    return _CACHE


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    """运营改配置:只接受已知键,upsert system_configs.grammar_config,并刷新缓存。"""
    clean = {k: v for k, v in (patch or {}).items() if k in DEFAULTS}
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    merged = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        merged.update(row.value)
    merged.update(clean)
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=merged,
                            description="R10 语法掌握/定级参数(阈值/复测/分级/纸质权重)",
                            updated_by=updated_by))
    else:
        row.value = merged
        row.updated_by = updated_by
    await db.flush()
    global _CACHE
    _CACHE = {k: merged.get(k, DEFAULTS[k]) for k in DEFAULTS}
    return _CACHE
