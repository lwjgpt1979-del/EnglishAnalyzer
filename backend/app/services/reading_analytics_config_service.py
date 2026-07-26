"""阅读学情·判弱阈值配置(system_configs.reading_analytics)。

运营可配(admin `/admin/reading-analytics-config`),`DEFAULTS` 仅缺失兜底;
实际值经 get_config 读取。参数含义见各键注释,消费端 reading_intensive_service.reading_analytics。
"""
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig

_KEY = "reading_analytics"

DEFAULTS: dict = {
    "weak_word_min_papers": 2,   # 考纲薄弱词出现 ≥N 卷 → 高频薄弱词
    "skill_min_sample": 3,       # 题型样本 ≥M 才判弱(样本太小不判)
    "skill_weak_rate": 60,       # 题型正确率 <X% 判弱
    "struct_min_stuck": 3,       # 某句法结构累计卡 ≥K 次 判弱
}


async def get_config(db: AsyncSession) -> dict:
    """当前阈值:后台配置覆盖默认;非法/缺失键走默认。"""
    cfg = dict(DEFAULTS)
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        cfg.update({k: v for k, v in row.value.items() if k in DEFAULTS})
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    """运营改阈值:只接受已知键、正整数;upsert system_configs.reading_analytics。"""
    clean: dict = {}
    for k, v in (patch or {}).items():
        if k not in DEFAULTS:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv > 0:                                    # 阈值须为正
            clean[k] = iv
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    merged = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        merged.update({k: v for k, v in row.value.items() if k in DEFAULTS})
    merged.update(clean)
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=merged,
                            description="阅读学情·判弱阈值(高频词卷数/题型样本与正确率/句法卡次数)",
                            updated_by=updated_by))
    else:
        row.value = merged
        row.updated_by = updated_by
    await db.commit()
    return merged
