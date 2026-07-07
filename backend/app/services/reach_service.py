"""触达任务:分群 × 渠道 × 文案 → 执行。渠道 = station(站内通知) / sales_lead(生成电销线索) / sms(营销短信)。

sales_lead 渠道 = 把存量用户(尤其将到期/流失会员)转成电销线索,喂已建好的电销 CRM,
座席直接拨号续费——「存量召回=电销同一块肌肉」的落点。

生命周期自动化:recurring=True 的任务由 cron(run_reach_campaigns)每日增量跑——只触达
「新进入分群且未被本任务触达过」的人(靠 reach_log 去重),状态停留 active。
one-shot(recurring=False)执行一次即 done。所有触达写 reach_log(审计 + 去重)。
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d23_sales_crm import SalesLead
from app.models.d24_reach import ReachCampaign, ReachLog, UserSegment
from app.services import notification_service, segment_service, sms_service

CHANNELS = ("station", "sales_lead", "sms")
_MAX_USERS = 5000              # 单次触达上限,防跑飞


async def list_campaigns(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    total = (await db.execute(sa.select(sa.func.count()).select_from(ReachCampaign))).scalar_one()
    rows = (await db.execute(sa.select(ReachCampaign)
            .order_by(ReachCampaign.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": int(total), "items": rows}


def _clean_variants(variants, channel: str) -> list | None:
    """校验并规整 A/B 变体。仅 station/sms 有意义;每个变体需 content。返回 None=单文案。"""
    if not variants:
        return None
    if channel not in ("station", "sms"):
        raise AppError(code=400, message="A/B 文案仅站内通知/短信渠道支持")
    if not isinstance(variants, list) or len(variants) < 2:
        raise AppError(code=400, message="A/B 至少要 2 个变体")
    out = []
    for i, v in enumerate(variants):
        if not isinstance(v, dict) or not (v.get("content") or "").strip():
            raise AppError(code=400, message=f"变体 {i + 1} 缺内容")
        out.append({"label": str(v.get("label") or chr(65 + i))[:8],
                    "title": v.get("title"), "content": v["content"]})
    return out


async def create_campaign(db: AsyncSession, *, name: str, channel: str, admin_id: uuid.UUID,
                          segment_id: uuid.UUID | None = None, rule: dict | None = None,
                          title: str | None = None, content: str | None = None,
                          lead_tag: str | None = None, recurring: bool = False,
                          variants: list | None = None) -> ReachCampaign:
    if channel not in CHANNELS:
        raise AppError(code=400, message=f"渠道非法 {channel!r},仅 {CHANNELS}")
    snap = rule
    if snap is None and segment_id is not None:
        seg = await db.get(UserSegment, segment_id)
        if seg is None:
            raise AppError(code=404, message="分群不存在")
        snap = seg.rule
    if snap is None:
        raise AppError(code=400, message="需指定分群或即席规则")
    segment_service.build_where(snap)   # 校验
    variants = _clean_variants(variants, channel)
    if channel in ("station", "sms") and not variants and not (content or "").strip():
        raise AppError(code=400, message="站内通知/短信需填内容")
    camp = ReachCampaign(
        id=uuid.uuid4(), name=name, segment_id=segment_id, rule_snapshot=snap,
        channel=channel, title=title, content=content, variants=variants, lead_tag=lead_tag,
        recurring=recurring, enabled=True, status="draft", created_by=admin_id)
    db.add(camp)
    await db.flush()
    return camp


async def set_enabled(db: AsyncSession, *, campaign_id: uuid.UUID, enabled: bool) -> ReachCampaign:
    camp = await db.get(ReachCampaign, campaign_id)
    if camp is None:
        raise AppError(code=404, message="触达任务不存在")
    camp.enabled = enabled
    await db.flush()
    return camp


async def _reached_ids(db: AsyncSession, campaign_id: uuid.UUID) -> set:
    return set((await db.execute(
        sa.select(ReachLog.user_id).where(ReachLog.campaign_id == campaign_id))).scalars().all())


def _log_reach(db: AsyncSession, camp: ReachCampaign, user_id: uuid.UUID,
               variant: str | None = None) -> None:
    db.add(ReachLog(id=uuid.uuid4(), campaign_id=camp.id, user_id=user_id,
                    channel=camp.channel, variant=variant))


def _pick_variant(camp: ReachCampaign, user_id: uuid.UUID):
    """按 user_id 稳定分流到某变体 → (title, content, label)。无 variants → 单文案。"""
    vs = camp.variants
    if not vs:
        return camp.title, camp.content, None
    idx = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16) % len(vs)
    v = vs[idx]
    return (v.get("title") or camp.title), v.get("content") or "", v.get("label")


async def run_campaign(db: AsyncSession, *, campaign_id: uuid.UUID) -> ReachCampaign:
    """执行触达:圈人 →(recurring 排除已触达)→ 按渠道下发 + 写 reach_log → 回填统计。

    one-shot:done 后不可重复跑。recurring:每次只触达新进入分群且未触达过的人,状态停留 active。
    """
    camp = await db.get(ReachCampaign, campaign_id)
    if camp is None:
        raise AppError(code=404, message="触达任务不存在")
    if camp.status == "done" and not camp.recurring:
        raise AppError(code=400, message="该任务已执行,不可重复跑")
    if not camp.enabled:
        raise AppError(code=400, message="任务已停用")

    rows = await segment_service.resolve_users(db, camp.rule_snapshot or {}, limit=_MAX_USERS)
    reached = await _reached_ids(db, camp.id)   # recurring 或重跑时去重
    todo = [r for r in rows if r.id not in reached]
    stats = {"matched": len(rows), "sent": 0, "failed": 0, "skipped": len(rows) - len(todo)}
    try:
        if camp.channel == "station":
            await _run_station(db, camp, todo, stats)
        elif camp.channel == "sms":
            await _run_sms(db, camp, todo, stats)
        elif camp.channel == "sales_lead":
            await _run_sales_lead(db, camp, todo, stats)
        else:
            raise AppError(code=400, message=f"渠道未实现 {camp.channel}")
        camp.status = "active" if camp.recurring else "done"
    except AppError:
        raise
    except Exception:  # noqa: BLE001
        camp.status = "failed"
        raise
    finally:
        camp.stats = stats
        camp.total_reached = (camp.total_reached or 0) + stats["sent"]
        camp.executed_at = datetime.now(timezone.utc)
        await db.flush()
    return camp


async def _run_station(db: AsyncSession, camp: ReachCampaign, rows, stats: dict) -> None:
    for r in rows:
        title, content, variant = _pick_variant(camp, r.id)
        try:
            await notification_service.emit(
                db, user_id=r.id, type_="membership", title=title or "来自好乐学的消息",
                content=content or "",
                meta={"reach_campaign_id": str(camp.id), "variant": variant})
            _log_reach(db, camp, r.id, variant)
            stats["sent"] += 1
        except Exception:  # noqa: BLE001
            stats["failed"] += 1


async def _run_sms(db: AsyncSession, camp: ReachCampaign, rows, stats: dict) -> None:
    """营销短信(dev-mock 记日志;生产走已报备营销模板 + 退订)。无手机号跳过。"""
    for r in rows:
        phone = (r.phone or "").strip()
        if not phone:
            stats["skipped"] += 1
            continue
        _title, content, variant = _pick_variant(camp, r.id)
        try:
            await sms_service.send_marketing(phone=phone, content=content or "")
            _log_reach(db, camp, r.id, variant)
            stats["sent"] += 1
        except Exception:  # noqa: BLE001
            stats["failed"] += 1


async def _run_sales_lead(db: AsyncSession, camp: ReachCampaign, rows, stats: dict) -> None:
    """存量用户 → 电销线索(按手机号去重,已在池中的跳过)。"""
    phones = [r.phone for r in rows if (r.phone or "").strip()]
    existing = set()
    if phones:
        existing = set((await db.execute(
            sa.select(SalesLead.phone).where(SalesLead.phone.in_(phones)))).scalars().all())
    tags = [camp.lead_tag] if camp.lead_tag else None
    note = f"存量召回·{camp.name}"[:255]
    for r in rows:
        phone = (r.phone or "").strip()
        if not phone or phone in existing:
            stats["skipped"] += 1                 # 无号 / 已在线索池
            continue
        db.add(SalesLead(
            id=uuid.uuid4(),
            name=(r.nickname or f"学员{phone[-4:]}")[:200],
            phone=phone, region_code=r.city_code, source="recall",
            source_note=note, tags=tags, status="new", pool="public"))
        _log_reach(db, camp, r.id)
        existing.add(phone)                        # 防同批重复号
        stats["sent"] += 1


# ── 生命周期自动化(cron)────────────────────────────────────────────────────

async def run_recurring_all(db: AsyncSession) -> dict:
    """cron 入口:跑所有 enabled 的 recurring 任务(增量)。返回汇总。"""
    camps = (await db.execute(sa.select(ReachCampaign).where(
        ReachCampaign.recurring.is_(True), ReachCampaign.enabled.is_(True)))).scalars().all()
    out = {"campaigns": 0, "sent": 0, "details": []}
    for camp in camps:
        try:
            c = await run_campaign(db, campaign_id=camp.id)
            await db.commit()
            out["campaigns"] += 1
            out["sent"] += (c.stats or {}).get("sent", 0)
            out["details"].append({"id": str(camp.id), "name": camp.name, "stats": c.stats})
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            out["details"].append({"id": str(camp.id), "name": camp.name, "error": str(exc)})
    return out


# ── 触达明细审计 ──────────────────────────────────────────────────────────────

async def get_logs(db: AsyncSession, *, campaign_id: uuid.UUID, skip: int = 0, limit: int = 50) -> dict:
    """某任务的触达明细(分页,左连 users 取昵称/手机)+ A/B 变体汇总。"""
    total = (await db.execute(sa.select(sa.func.count()).select_from(ReachLog)
             .where(ReachLog.campaign_id == campaign_id))).scalar_one()
    rows = (await db.execute(
        sa.select(ReachLog.user_id, ReachLog.channel, ReachLog.variant, ReachLog.reached_at,
                  User.nickname, User.phone)
        .outerjoin(User, User.id == ReachLog.user_id)
        .where(ReachLog.campaign_id == campaign_id)
        .order_by(ReachLog.reached_at.desc()).offset(skip).limit(limit))).all()
    summary = (await db.execute(
        sa.select(ReachLog.variant, sa.func.count()).where(ReachLog.campaign_id == campaign_id)
        .group_by(ReachLog.variant))).all()
    return {
        "total": int(total),
        "items": [{"user_id": str(r.user_id), "nickname": r.nickname, "phone": r.phone,
                   "channel": r.channel, "variant": r.variant,
                   "reached_at": r.reached_at.isoformat() if r.reached_at else None} for r in rows],
        "variant_summary": [{"variant": v or "(单文案)", "count": int(n)} for v, n in summary],
    }
