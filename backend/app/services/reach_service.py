"""触达任务:分群 × 渠道 × 文案 → 执行。渠道 MVP = station(站内通知) / sales_lead(生成电销线索)。

sales_lead 渠道 = 把存量用户(尤其将到期/流失会员)转成电销线索,喂已建好的电销 CRM,
座席直接拨号续费——「存量召回=电销同一块肌肉」的落点。按手机号去重,已在池中的跳过。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d23_sales_crm import SalesLead
from app.models.d24_reach import ReachCampaign, UserSegment
from app.services import notification_service, segment_service

CHANNELS = ("station", "sales_lead")
_MAX_USERS = 5000              # 单次触达上限,防跑飞


async def list_campaigns(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    total = (await db.execute(sa.select(sa.func.count()).select_from(ReachCampaign))).scalar_one()
    rows = (await db.execute(sa.select(ReachCampaign)
            .order_by(ReachCampaign.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": int(total), "items": rows}


async def create_campaign(db: AsyncSession, *, name: str, channel: str, admin_id: uuid.UUID,
                          segment_id: uuid.UUID | None = None, rule: dict | None = None,
                          title: str | None = None, content: str | None = None,
                          lead_tag: str | None = None) -> ReachCampaign:
    if channel not in CHANNELS:
        raise AppError(code=400, message=f"渠道非法 {channel!r},仅 {CHANNELS}")
    # 规则:优先用传入 rule(即席),否则取分群的 rule
    snap = rule
    if snap is None and segment_id is not None:
        seg = await db.get(UserSegment, segment_id)
        if seg is None:
            raise AppError(code=404, message="分群不存在")
        snap = seg.rule
    if snap is None:
        raise AppError(code=400, message="需指定分群或即席规则")
    segment_service.build_where(snap)   # 校验
    if channel == "station" and not (content or "").strip():
        raise AppError(code=400, message="站内通知需填内容")
    camp = ReachCampaign(
        id=uuid.uuid4(), name=name, segment_id=segment_id, rule_snapshot=snap,
        channel=channel, title=title, content=content, lead_tag=lead_tag,
        status="draft", created_by=admin_id)
    db.add(camp)
    await db.flush()
    return camp


async def run_campaign(db: AsyncSession, *, campaign_id: uuid.UUID) -> ReachCampaign:
    """执行触达:圈人 → 按渠道下发 → 回填 stats/status/executed_at。draft 才可跑。"""
    camp = await db.get(ReachCampaign, campaign_id)
    if camp is None:
        raise AppError(code=404, message="触达任务不存在")
    if camp.status == "done":
        raise AppError(code=400, message="该任务已执行,不可重复跑")
    rule = camp.rule_snapshot or {}
    rows = await segment_service.resolve_users(db, rule, limit=_MAX_USERS)
    stats = {"matched": len(rows), "sent": 0, "failed": 0, "skipped": 0}
    try:
        if camp.channel == "station":
            await _run_station(db, camp, rows, stats)
        elif camp.channel == "sales_lead":
            await _run_sales_lead(db, camp, rows, stats)
        else:
            raise AppError(code=400, message=f"渠道未实现 {camp.channel}")
        camp.status = "done"
    except AppError:
        raise
    except Exception:  # noqa: BLE001
        camp.status = "failed"
        raise
    finally:
        camp.stats = stats
        camp.executed_at = datetime.now(timezone.utc)
        await db.flush()
    return camp


async def _run_station(db: AsyncSession, camp: ReachCampaign, rows, stats: dict) -> None:
    title = camp.title or "来自好乐学的消息"
    for r in rows:
        try:
            await notification_service.emit(
                db, user_id=r.id, type_="membership", title=title, content=camp.content or "",
                meta={"reach_campaign_id": str(camp.id)})
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
        if not phone:
            stats["skipped"] += 1                 # 无号无法外呼
            continue
        if phone in existing:
            stats["skipped"] += 1                 # 已在线索池
            continue
        db.add(SalesLead(
            id=uuid.uuid4(),
            name=(r.nickname or f"学员{phone[-4:]}")[:200],
            phone=phone, region_code=r.city_code, source="recall",
            source_note=note, tags=tags, status="new", pool="public"))
        existing.add(phone)                        # 防同批重复号
        stats["sent"] += 1
