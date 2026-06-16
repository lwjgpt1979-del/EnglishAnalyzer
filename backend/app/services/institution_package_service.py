"""机构套餐（§9.1 / §5.6）——全配置驱动，代码不写死任何配额数字。

档位定义 + 各档配额 + 预警阈值 + 重置日 全在 system_configs.institution_packages
（一份 JSON，运营后台可增删档位/改数字，不发版、不迁移枚举）。
机构维度只存所选 package_tier + 可选 override（定制/微调）。
三类用量（老师席位/月出卷池/月批改池）按现有表实时聚合，无计数表。

本模块属 S1：建模 + 配置 + 有效配额解析 + 用量只读。扣减闸门在 S2。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution, Teacher, User
from app.models.d9_system import SystemConfig

_KEY = "institution_packages"

# 首次播种默认（仅配置缺失时兜底；任何时候后台写入值优先，可被覆盖）。
DEFAULT_CONFIG = {
    "tiers": [
        {"key": "starter", "name": "入门包", "teacher_seats": 5, "paper_pool": 100, "grading_pool": 500},
        {"key": "standard", "name": "标准包", "teacher_seats": 20, "paper_pool": 400, "grading_pool": 2000},
        {"key": "flagship", "name": "旗舰包", "teacher_seats": 50, "paper_pool": 1000, "grading_pool": 5000},
    ],
    "warn_threshold_pct": 20,
    "reset_day": 1,
}
_TIER_FIELDS = ("teacher_seats", "paper_pool", "grading_pool")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── 配置读写（单一来源）──────────────────────────────────────────────────────
async def get_config(db: AsyncSession) -> dict:
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None or not isinstance(cfg.value, dict):
        return {**DEFAULT_CONFIG, "tiers": [dict(t) for t in DEFAULT_CONFIG["tiers"]]}
    v = cfg.value
    return {
        "tiers": v.get("tiers") or [dict(t) for t in DEFAULT_CONFIG["tiers"]],
        "warn_threshold_pct": int(v.get("warn_threshold_pct", DEFAULT_CONFIG["warn_threshold_pct"])),
        "reset_day": int(v.get("reset_day", DEFAULT_CONFIG["reset_day"])),
    }


async def update_config(db: AsyncSession, *, config: dict, admin_id: uuid.UUID) -> dict:
    tiers = config.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise AppError(code=400, message="至少保留一个套餐档位")
    seen = set()
    norm_tiers = []
    for t in tiers:
        key = str(t.get("key", "")).strip()
        if not key:
            raise AppError(code=400, message="档位 key 不能为空")
        if key in seen:
            raise AppError(code=400, message=f"档位 key 重复：{key}")
        seen.add(key)
        nt = {"key": key[:20], "name": str(t.get("name", key)).strip()[:40]}
        for f in _TIER_FIELDS:
            val = int(t.get(f, 0) or 0)
            if val < 0:
                raise AppError(code=400, message=f"{key}.{f} 不能为负")
            nt[f] = val
        norm_tiers.append(nt)
    wt = int(config.get("warn_threshold_pct", DEFAULT_CONFIG["warn_threshold_pct"]))
    rd = int(config.get("reset_day", DEFAULT_CONFIG["reset_day"]))
    if not (0 <= wt <= 100):
        raise AppError(code=400, message="预警阈值需在 0-100")
    if not (1 <= rd <= 28):
        raise AppError(code=400, message="月度重置日需在 1-28")
    payload = {"tiers": norm_tiers, "warn_threshold_pct": wt, "reset_day": rd}
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=payload,
                            description="机构套餐档位与配额（§9.1/§5.6，配置驱动）",
                            updated_by=admin_id))
    else:
        cfg.value = payload
        cfg.updated_by = admin_id
    await db.flush()
    return payload


# ── 有效配额解析（档位默认 → 机构 override）────────────────────────────────────
async def effective_for(db: AsyncSession, institution: Institution) -> dict | None:
    """机构有效配额；package_tier 为空 → None（非套餐机构，不受机构池限制）。"""
    if not institution.package_tier:
        return None
    cfg = await get_config(db)
    base = next((t for t in cfg["tiers"] if t["key"] == institution.package_tier), {})

    def _resolve(field: str, override):
        if override is not None:
            return int(override)
        return int(base.get(field, 0))

    return {
        "package_tier": institution.package_tier,
        "package_name": base.get("name", institution.package_tier),
        "is_custom": not base,   # 档位不在配置列表（如 custom）→ 全靠 override
        "teacher_seats": _resolve("teacher_seats", institution.teacher_seats_override),
        "paper_pool": _resolve("paper_pool", institution.paper_pool_override),
        "grading_pool": _resolve("grading_pool", institution.grading_pool_override),
        "warn_threshold_pct": cfg["warn_threshold_pct"],
        "reset_day": cfg["reset_day"],
    }


def month_start(reset_day: int, now: dt.datetime | None = None) -> dt.datetime:
    now = now or _now()
    rd = max(1, min(28, reset_day or 1))
    start = now.replace(day=rd, hour=0, minute=0, second=0, microsecond=0)
    if now.day < rd:
        return (start.replace(day=1) - dt.timedelta(days=1)).replace(
            day=rd, hour=0, minute=0, second=0, microsecond=0)
    return start


# ── 用量（按机构汇总现有表，无计数表）────────────────────────────────────────
async def _seats_used(db: AsyncSession, institution_id: uuid.UUID) -> int:
    return int(await db.scalar(
        select(func.count()).select_from(Teacher).where(
            Teacher.institution_id == institution_id)) or 0)


async def _paper_used(db: AsyncSession, institution_id: uuid.UUID, since: dt.datetime) -> int:
    from app.models.d7_teacher import Assignment
    return int(await db.scalar(
        select(func.count()).select_from(Assignment)
        .join(Teacher, Teacher.id == Assignment.teacher_id)
        .where(Teacher.institution_id == institution_id, Assignment.created_at >= since)) or 0)


async def _grading_used(db: AsyncSession, institution_id: uuid.UUID, since: dt.datetime) -> int:
    from app.models.d3_wrong_questions import TeacherComment
    return int(await db.scalar(
        select(func.count()).select_from(TeacherComment)
        .join(Teacher, Teacher.id == TeacherComment.teacher_id)
        .where(Teacher.institution_id == institution_id, TeacherComment.created_at >= since)) or 0)


async def usage_overview(db: AsyncSession, *, institution_id: uuid.UUID) -> dict:
    """机构套餐 + 三类池用量（S1 只读展示用）。非套餐机构返回 {package_tier: None}。"""
    inst = await db.get(Institution, institution_id)
    if inst is None:
        raise AppError(code=404, message="机构不存在")
    eff = await effective_for(db, inst)
    if eff is None:
        return {"package_tier": None}
    ms = month_start(eff["reset_day"])
    seats = await _seats_used(db, institution_id)
    paper = await _paper_used(db, institution_id, ms)
    grading = await _grading_used(db, institution_id, ms)

    def _blk(used, limit):
        remain = max(0, limit - used)
        return {"used": used, "limit": limit, "remaining": remain,
                "remaining_pct": round(remain / limit * 100, 1) if limit else 100.0}
    return {
        "package_tier": eff["package_tier"], "package_name": eff["package_name"],
        "is_custom": eff["is_custom"], "warn_threshold_pct": eff["warn_threshold_pct"],
        "reset_day": eff["reset_day"],
        "teacher_seats": _blk(seats, eff["teacher_seats"]),
        "paper": _blk(paper, eff["paper_pool"]),
        "grading": _blk(grading, eff["grading_pool"]),
    }


# ── S2 机构池闸门（机构老师出卷/批改扣机构池 + 池内老师子上限 + 池预警）────────
async def _institution_admin_ids(db: AsyncSession, institution_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        select(User.id).where(User.role == "institution_admin",
                              User.institution_id == institution_id,
                              User.is_active.is_(True)))).scalars().all())


async def _maybe_pool_warn(db: AsyncSession, *, institution_id: uuid.UUID, eff: dict,
                           kind: str, label: str, pool_used_after: int) -> None:
    limit, thr = eff[f"{kind}_pool"], eff["warn_threshold_pct"]
    if limit <= 0 or thr <= 0:
        return
    warn_line = limit * (100 - thr) / 100.0
    if (pool_used_after - 1) < warn_line <= pool_used_after:   # 恰好本次越线 → 一次
        remain = max(0, limit - pool_used_after)
        from app.services import notification_service
        for aid in await _institution_admin_ids(db, institution_id):
            try:
                await notification_service.emit(
                    db, user_id=aid, type_="system", title="机构额度预警",
                    content=f"本机构本月「{label}」额度仅剩 {remain}/{limit}，请合理安排或联系平台扩容。",
                    meta={"kind": f"pool_{kind}"})
            except Exception:
                pass


async def _gate(db: AsyncSession, *, teacher: Teacher, kind: str, label: str) -> bool:
    """机构老师 出卷(paper)/批改(grading) 池闸门。
    返回 True=按机构池处理（已通过）；False=非套餐机构（调用方回退个体逻辑）。"""
    if teacher is None or not teacher.institution_id:
        return False
    inst = await db.get(Institution, teacher.institution_id)
    eff = await effective_for(db, inst) if inst else None
    if eff is None:
        return False   # 机构未配套餐 → 走个体逻辑
    ms = month_start(eff["reset_day"])
    pool_used = (await _paper_used(db, inst.id, ms) if kind == "paper"
                 else await _grading_used(db, inst.id, ms))
    pool_limit = eff[f"{kind}_pool"]
    if pool_used >= pool_limit:
        raise AppError(code=403, message=f"机构本月{label}额度已用尽，请联系机构管理员")
    # 池内老师子上限（机构管理员可为单个老师设；null=共享池先到先得）
    sub = teacher.monthly_paper_quota if kind == "paper" else teacher.monthly_grading_quota
    if sub is not None:
        from app.services import teacher_limit_service as _tl
        ms_t = _tl._month_start(eff["reset_day"])
        my = (await _tl._paper_used(db, teacher.id, ms_t) if kind == "paper"
              else await _tl._grading_used(db, teacher.id, ms_t))
        if my >= sub:
            raise AppError(code=403, message=f"您的{label}子额度已用尽（{sub}/月），请联系机构管理员")
    await _maybe_pool_warn(db, institution_id=inst.id, eff=eff, kind=kind,
                           label=label, pool_used_after=pool_used + 1)
    return True


async def assert_can_add_teacher(db: AsyncSession, *, institution_id: uuid.UUID) -> None:
    """S3：机构加老师前校验席位上限。非套餐机构（无 package_tier）不限制。"""
    inst = await db.get(Institution, institution_id)
    eff = await effective_for(db, inst) if inst else None
    if eff is None:
        return
    used = await _seats_used(db, institution_id)
    if used >= eff["teacher_seats"]:
        raise AppError(code=403,
                       message=f"机构老师席位已满（{eff['teacher_seats']}个），请联系平台升级套餐")


async def gate_paper(db: AsyncSession, *, teacher: Teacher) -> bool:
    return await _gate(db, teacher=teacher, kind="paper", label="出卷")


async def gate_grading(db: AsyncSession, *, teacher: Teacher) -> bool:
    return await _gate(db, teacher=teacher, kind="grading", label="批改/点评")


# ── 管理：给机构指定套餐 / 覆盖 ───────────────────────────────────────────────
async def set_institution_package(db: AsyncSession, *, institution_id: uuid.UUID,
                                  package_tier: str | None, overrides: dict | None = None) -> Institution:
    inst = await db.get(Institution, institution_id)
    if inst is None:
        raise AppError(code=404, message="机构不存在")
    pt = (package_tier or "").strip() or None
    if pt:
        cfg = await get_config(db)
        known = {t["key"] for t in cfg["tiers"]}
        if pt != "custom" and pt not in known:
            raise AppError(code=400, message=f"未知套餐档位：{pt}（请先在套餐配置中新增）")
    inst.package_tier = pt
    ov = overrides or {}
    for col in ("teacher_seats_override", "paper_pool_override", "grading_pool_override"):
        if col in ov:
            val = ov[col]
            setattr(inst, col, int(val) if val not in (None, "") else None)
    await db.flush()
    return inst
