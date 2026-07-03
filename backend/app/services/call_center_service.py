"""呼叫中心接入(通用中转 webhook):通话结束回调 → 映射字段 → 落 call 跟进 + 挂录音 → 触发 ASR/意向分析。

各家服务商(天润融通/容联七陌/阿里云呼叫中心…)回调字段不同,故用**可配置字段映射**
(system_configs.call_center.field_map)把它们的字段名映射成我们内部字段,换服务商只改配置不改码。
webhook 是外部服务器直连(无登录),用 webhook_token 鉴权。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.models.d23_sales_crm import SalesLead

_log = logging.getLogger(__name__)
_KEY = "call_center"

# 内部字段 → 默认取自回调 body 的哪个键(常见形态;换服务商在后台改 field_map)
DEFAULTS: dict = {
    "webhook_token": "",                 # 校验回调来源(在服务商后台配同一串)
    "auto_transcribe": True,             # 有录音 → 自动 ASR + 意向分析
    "field_map": {
        "lead_id": "biz_id",             # 我们发起呼叫时带的自定义参数(可选,精确关联)
        "phone": "callee",               # 被叫号(客户号)——无 lead_id 时按此匹配线索
        "recording_url": "record_url",   # 录音地址
        "call_duration_sec": "duration",
        "outcome": "status",             # connected/no_answer/…
        "direction": "direction",
    },
}


async def get_config(db: AsyncSession) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    cfg = {**DEFAULTS, "field_map": dict(DEFAULTS["field_map"])}
    if row is not None and isinstance(row.value, dict):
        for k in ("webhook_token", "auto_transcribe"):
            if k in row.value:
                cfg[k] = row.value[k]
        if isinstance(row.value.get("field_map"), dict):
            cfg["field_map"].update(row.value["field_map"])
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    val = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    for k in ("webhook_token", "auto_transcribe"):
        if k in patch:
            val[k] = patch[k]
    if isinstance(patch.get("field_map"), dict):
        val["field_map"] = {**(val.get("field_map") or {}), **patch["field_map"]}
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=val,
                            description="呼叫中心接入(webhook token / 字段映射 / 自动转写)",
                            updated_by=updated_by))
    else:
        row.value = val
        row.updated_by = updated_by
    await db.flush()
    return await get_config(db)


def parse_webhook(body: dict, field_map: dict) -> dict:
    """按 field_map 把服务商回调 body → 内部字段。"""
    return {inner: body.get(src) for inner, src in field_map.items()}


async def handle_webhook(db: AsyncSession, *, body: dict) -> dict:
    """落一条 call 跟进(挂录音)。返回 {matched, lead_id, activity_id, has_recording}。"""
    from app.services import sales_analysis_service as ana
    cfg = await get_config(db)
    p = parse_webhook(body, cfg["field_map"])

    lead_id = None
    if p.get("lead_id"):
        try:
            lead_id = uuid.UUID(str(p["lead_id"]))
        except (ValueError, TypeError):
            lead_id = None
    if lead_id is None and p.get("phone"):
        phone = str(p["phone"]).strip()
        lead_id = (await db.execute(sa.select(SalesLead.id)
                   .where(SalesLead.phone == phone).limit(1))).scalar_one_or_none()
    if lead_id is None:
        return {"matched": False, "lead_id": None, "activity_id": None, "has_recording": False}

    dur = p.get("call_duration_sec")
    act = await ana.ingest_call_record(
        db, lead_id=lead_id, admin_id=None,
        recording_url=(str(p["recording_url"]) if p.get("recording_url") else None),
        asr_text=None, call_duration_sec=int(dur) if dur else None,
        direction=str(p.get("direction") or "out"),
        outcome=str(p["outcome"]) if p.get("outcome") else None)
    return {"matched": True, "lead_id": str(lead_id), "activity_id": str(act.id),
            "has_recording": bool(act.recording_url)}


# ── 后台 ASR + 意向分析(不阻塞 webhook 返回)────────────────────────────────

_tasks: set[asyncio.Task] = set()


def schedule_transcribe(activity_id: uuid.UUID) -> None:
    """fire-and-forget:后台 ASR 转写 + 意向分析(录音文件识别耗时,别卡 webhook)。"""
    t = asyncio.create_task(_run_transcribe(activity_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _run_transcribe(activity_id: uuid.UUID) -> None:
    from app.core.database import _async_session_factory
    from app.services import sales_analysis_service as ana
    try:
        async with _async_session_factory() as s:
            await ana.transcribe_and_analyze(s, activity_id=activity_id)
            await s.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning("后台转写分析失败 activity=%s: %s", activity_id, exc)
