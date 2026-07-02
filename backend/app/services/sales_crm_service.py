"""电销 CRM 服务(P0):线索池 + 公海/私海 + 跟进 + 赢单画像反查推荐。

外呼/ASR/意向分析(P1)、企微存档(P2)后续接入;本层只做零第三方依赖的闭环。
运营可配置值(公海回收天数、推荐权重等)读 system_configs.sales_crm,禁写死。
方案见 docs/电销CRM-方案设计.md。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SystemConfig
from app.models.d23_sales_crm import SalesLead, SalesLeadActivity
from app.services import region_service

_CFG_KEY = "sales_crm"

# 常量仅兜底/白名单;实际值见 get_config()(system_configs.sales_crm)。
DEFAULTS: dict = {
    "public_pool_recycle_days": 7,      # 私海 N 天未跟进 → 回收公海
    "recommend_weights": {              # 赢单画像反查各维度权重
        "industry": 3.0, "province": 1.0, "city": 2.0, "tag": 1.0,
    },
    "intent_grade_thresholds": {        # 意向分 → 分层(A/B/C,其余 D)
        "A": 80, "B": 60, "C": 40,
    },
}

STATUSES = ("new", "contacted", "interested", "negotiating", "won", "lost", "invalid")
SOURCES = ("baidu_map", "meituan", "dianping", "tungee", "manual", "import", "other")
CHANNELS = ("call", "wechat", "note", "sms")


async def get_config(db: AsyncSession) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    cfg = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        for k in DEFAULTS:
            if k in row.value:
                cfg[k] = row.value[k]
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    clean = {k: v for k, v in (patch or {}).items() if k in DEFAULTS}
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    merged = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        merged.update(row.value)
    merged.update(clean)
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_CFG_KEY, value=merged,
                            description="电销 CRM 参数(公海回收天数/推荐权重)", updated_by=updated_by))
    else:
        row.value = merged
        row.updated_by = updated_by
    await db.flush()
    return {k: merged.get(k, DEFAULTS[k]) for k in DEFAULTS}


# ── 线索 CRUD / 池 ────────────────────────────────────────────────────────────

async def _resolve_region(db: AsyncSession, *, region_code: str | None,
                          region_name: str | None) -> tuple[str | None, str | None]:
    """地区一律走 region_service:有码用码取名;只有名字则 region_from_name 反解。"""
    if region_code:
        return region_code, region_name
    if region_name:
        code, name = await region_service.region_from_name(db, region_name)
        if code:
            return code, name or region_name
    return None, region_name


async def create_lead(db: AsyncSession, *, data: dict) -> SalesLead:
    rc, rn = await _resolve_region(
        db, region_code=data.get("region_code"), region_name=data.get("region_name"))
    lead = SalesLead(
        id=uuid.uuid4(),
        name=(data.get("name") or "").strip() or "未命名线索",
        contact_name=data.get("contact_name"),
        phone=(data.get("phone") or "").strip() or None,
        wechat_id=data.get("wechat_id"),
        address=data.get("address"),
        region_code=rc, region_name=rn,
        industry=data.get("industry"),
        biz_tags=data.get("biz_tags"),
        source=data.get("source") if data.get("source") in SOURCES else "manual",
        source_note=data.get("source_note"),
        status="new",
        consent=bool(data.get("consent", False)),
        dnc=bool(data.get("dnc", False)),
        pool="public",
    )
    db.add(lead)
    await db.flush()
    return lead


async def import_leads(db: AsyncSession, *, items: list[dict], source: str = "import") -> dict:
    """批量导入:按 phone 去重(已存在则跳过)。返回 {created, skipped}。"""
    created = skipped = 0
    phones = [(it.get("phone") or "").strip() for it in items if (it.get("phone") or "").strip()]
    existing: set[str] = set()
    if phones:
        existing = set((await db.execute(
            sa.select(SalesLead.phone).where(SalesLead.phone.in_(phones)))).scalars().all())
    for it in items:
        phone = (it.get("phone") or "").strip()
        if phone and phone in existing:
            skipped += 1
            continue
        it = dict(it)
        it.setdefault("source", source)
        await create_lead(db, data=it)
        if phone:
            existing.add(phone)
        created += 1
    return {"created": created, "skipped": skipped}


async def list_leads(
    db: AsyncSession, *, pool: str | None = None, status: str | None = None,
    source: str | None = None, region_code: str | None = None,
    owner_admin_id: uuid.UUID | None = None, dnc: bool | None = None,
    due: bool = False, q: str | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[SalesLead], int]:
    base = sa.select(SalesLead)
    if pool:
        base = base.where(SalesLead.pool == pool)
    if status:
        base = base.where(SalesLead.status == status)
    if source:
        base = base.where(SalesLead.source == source)
    if region_code:               # 前缀:省码含其下所有市
        base = base.where(SalesLead.region_code.like(f"{region_code}%"))
    if owner_admin_id is not None:
        base = base.where(SalesLead.owner_admin_id == owner_admin_id)
    if dnc is not None:
        base = base.where(SalesLead.dnc.is_(dnc))
    if due:                       # 今日待办:已到跟进时间、且未到终态
        base = base.where(
            SalesLead.next_follow_at.isnot(None),
            SalesLead.next_follow_at <= datetime.now(timezone.utc),
            SalesLead.status.notin_(("won", "lost", "invalid")))
    if q:
        like = f"%{q}%"
        base = base.where(sa.or_(SalesLead.name.ilike(like),
                                 SalesLead.phone.ilike(like),
                                 SalesLead.contact_name.ilike(like)))
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(SalesLead.next_follow_at.asc().nullslast(),
                      SalesLead.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def get_lead(db: AsyncSession, lead_id: uuid.UUID) -> SalesLead:
    lead = await db.get(SalesLead, lead_id)
    if lead is None:
        raise AppError(code=404, message="线索不存在")
    return lead


_EDITABLE = {"name", "contact_name", "phone", "wechat_id", "address", "industry",
             "biz_tags", "source_note", "consent", "dnc", "next_follow_at",
             "intent_score", "intent_grade"}


async def update_lead(db: AsyncSession, *, lead_id: uuid.UUID, patch: dict) -> SalesLead:
    lead = await get_lead(db, lead_id)
    for k, v in (patch or {}).items():
        if k in _EDITABLE:
            setattr(lead, k, v)
    if "status" in (patch or {}) and patch["status"] in STATUSES:
        lead.status = patch["status"]
    if "region_code" in (patch or {}) or "region_name" in (patch or {}):
        rc, rn = await _resolve_region(
            db, region_code=patch.get("region_code"), region_name=patch.get("region_name"))
        lead.region_code, lead.region_name = rc, rn
    await db.flush()
    return lead


async def claim_lead(db: AsyncSession, *, lead_id: uuid.UUID, admin_id: uuid.UUID) -> SalesLead:
    """认领进私海。已被他人认领则拒绝(防撞单)。"""
    lead = await get_lead(db, lead_id)
    if lead.pool == "private" and lead.owner_admin_id not in (None, admin_id):
        raise AppError(code=409, message="该线索已被他人认领")
    lead.pool = "private"
    lead.owner_admin_id = admin_id
    lead.claimed_at = datetime.now(timezone.utc)
    await db.flush()
    return lead


async def release_lead(db: AsyncSession, *, lead_id: uuid.UUID) -> SalesLead:
    """退回公海。"""
    lead = await get_lead(db, lead_id)
    lead.pool = "public"
    lead.owner_admin_id = None
    lead.claimed_at = None
    await db.flush()
    return lead


async def recycle_public_pool(db: AsyncSession) -> int:
    """私海超 N 天未跟进(last_contacted_at / claimed_at 取新者为基准)→ 回收公海。返回回收数。"""
    cfg = await get_config(db)
    days = int(cfg["public_pool_recycle_days"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stale = (await db.execute(sa.select(SalesLead).where(
        SalesLead.pool == "private",
        sa.func.coalesce(SalesLead.last_contacted_at, SalesLead.claimed_at) < cutoff,
        SalesLead.status.notin_(("won", "negotiating")),   # 谈单中/已成不回收
    ))).scalars().all()
    for lead in stale:
        lead.pool = "public"
        lead.owner_admin_id = None
        lead.claimed_at = None
    await db.flush()
    return len(stale)


# ── 跟进记录 ──────────────────────────────────────────────────────────────────

async def add_activity(
    db: AsyncSession, *, lead_id: uuid.UUID, admin_id: uuid.UUID | None,
    channel: str, content: str | None = None, direction: str | None = None,
    outcome: str | None = None, next_follow_at: datetime | None = None,
    status: str | None = None,
) -> SalesLeadActivity:
    lead = await get_lead(db, lead_id)
    if channel not in CHANNELS:
        raise AppError(code=400, message="非法跟进方式")
    act = SalesLeadActivity(
        id=uuid.uuid4(), lead_id=lead_id, admin_id=admin_id,
        channel=channel, direction=direction, content=content, outcome=outcome)
    db.add(act)
    lead.last_contacted_at = datetime.now(timezone.utc)
    if next_follow_at is not None:
        lead.next_follow_at = next_follow_at
    if status and status in STATUSES:
        lead.status = status
    elif lead.status == "new":       # 首次触达自动推进
        lead.status = "contacted"
    await db.flush()
    return act


async def list_activities(
    db: AsyncSession, *, lead_id: uuid.UUID, skip: int = 0, limit: int = 20,
) -> tuple[list[SalesLeadActivity], int]:
    base = sa.select(SalesLeadActivity).where(SalesLeadActivity.lead_id == lead_id)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(SalesLeadActivity.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


# ── 赢单画像反查推荐(P0 纯查询自研) ────────────────────────────────────────

_RECO_CANDIDATE_CAP = 2000    # 打分候选上限,超出按 next_follow/created 序截断(避免全表扫)


async def recommend(
    db: AsyncSession, *, skip: int = 0, limit: int = 20,
) -> tuple[list[SalesLead], int]:
    """探迹式相似推荐:用 status=won 线索画像(行业/省/市/经营标签)给公海新线索打分。

    返回按 similar_score 降序的公海 new 线索页;顺带把分写回 similar_score。
    """
    cfg = await get_config(db)
    w = {**DEFAULTS["recommend_weights"], **(cfg.get("recommend_weights") or {})}

    won = (await db.execute(sa.select(
        SalesLead.industry, SalesLead.region_code, SalesLead.biz_tags
    ).where(SalesLead.status == "won"))).all()

    ind_set: set[str] = set()
    prov_set: set[str] = set()
    city_set: set[str] = set()
    tag_set: set[str] = set()
    for ind, rc, tags in won:
        if ind:
            ind_set.add(ind)
        if rc:
            prov_set.add(rc[:2])
            if len(rc) >= 4:
                city_set.add(rc[:4])
        if isinstance(tags, list):
            tag_set.update(str(t) for t in tags)

    cands = (await db.execute(sa.select(SalesLead).where(
        SalesLead.pool == "public", SalesLead.status == "new"
    ).order_by(SalesLead.next_follow_at.asc().nullslast(),
               SalesLead.created_at.desc()).limit(_RECO_CANDIDATE_CAP))).scalars().all()

    scored: list[tuple[float, SalesLead]] = []
    for c in cands:
        s = 0.0
        if not won:
            s = 0.0                              # 无赢单样本 → 全 0,退化为普通公海列表
        else:
            if c.industry and c.industry in ind_set:
                s += w["industry"]
            if c.region_code:
                if c.region_code[:2] in prov_set:
                    s += w["province"]
                if len(c.region_code) >= 4 and c.region_code[:4] in city_set:
                    s += w["city"]
            if isinstance(c.biz_tags, list) and tag_set:
                overlap = len({str(t) for t in c.biz_tags} & tag_set)
                s += w["tag"] * overlap
        c.similar_score = s
        scored.append((s, c))

    scored.sort(key=lambda x: (-x[0], x[1].created_at and 0))
    await db.flush()
    total = len(scored)
    page = [c for _s, c in scored[skip:skip + limit]]
    return page, total


# ── 座席看板 ──────────────────────────────────────────────────────────────────

_CN_TZ = timezone(timedelta(hours=8))    # 「今日」按东八区(业务在国内)


def _today_start_utc() -> datetime:
    now_cn = datetime.now(_CN_TZ)
    return now_cn.replace(hour=0, minute=0, second=0, microsecond=0)


async def board_stats(db: AsyncSession, *, admin_id: uuid.UUID | None = None) -> dict:
    """座席看板:线索分布 + 今日拨打量/接通率/今日新增 + 我的待办数。"""
    by_status = dict((await db.execute(
        sa.select(SalesLead.status, sa.func.count()).group_by(SalesLead.status))).all())
    by_pool = dict((await db.execute(
        sa.select(SalesLead.pool, sa.func.count()).group_by(SalesLead.pool))).all())
    total = (await db.execute(sa.select(sa.func.count()).select_from(SalesLead))).scalar_one()

    today = _today_start_utc()
    now = datetime.now(timezone.utc)
    today_new = (await db.execute(sa.select(sa.func.count()).where(
        SalesLead.created_at >= today))).scalar_one()
    today_calls = (await db.execute(sa.select(sa.func.count()).where(
        SalesLeadActivity.channel == "call",
        SalesLeadActivity.created_at >= today))).scalar_one()
    today_connected = (await db.execute(sa.select(sa.func.count()).where(
        SalesLeadActivity.channel == "call",
        SalesLeadActivity.outcome == "connected",
        SalesLeadActivity.created_at >= today))).scalar_one()
    # 待办:已到跟进时间、未到终态(admin 指定则只算其私海)
    due_q = sa.select(sa.func.count()).where(
        SalesLead.next_follow_at.isnot(None), SalesLead.next_follow_at <= now,
        SalesLead.status.notin_(("won", "lost", "invalid")))
    if admin_id is not None:
        due_q = due_q.where(SalesLead.owner_admin_id == admin_id)
    my_due = (await db.execute(due_q)).scalar_one()

    return {
        "total": int(total),
        "by_status": {k: int(v) for k, v in by_status.items()},
        "by_pool": {k: int(v) for k, v in by_pool.items()},
        "today_new": int(today_new),
        "today_calls": int(today_calls),
        "today_connected": int(today_connected),
        "connect_rate": round(today_connected / today_calls, 3) if today_calls else 0.0,
        "my_due": int(my_due),
    }
