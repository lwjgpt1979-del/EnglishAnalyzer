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
    "provider": "generic",               # generic=通用推送 webhook(天润/七陌/合力等) | aliyun_ccc=阿里云 CCC 拉取
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
    # 多服务商并行:每家独立 token/字段映射/开关,回调带 ?vendor=key 区分。
    # 结构:{key: {label, enabled, webhook_token, recording_url_prefix, field_map}}
    "vendors": {},
}

# 服务商模板(⚠️ 字段名是各家常见形态,签约后按真实话单文档校准;实际配置存 system_configs)
VENDOR_PRESETS: dict = {
    "qimo": {
        "label": "容联七陌",
        "enabled": True,
        "webhook_token": "",
        "recording_url_prefix": "",       # 七陌录音常给相对路径,拿到文档后填域名前缀
        "field_map": {
            "phone": "CalledNo", "recording_url": "RecordFile",
            "call_duration_sec": "CallTimeLength", "outcome": "State",
            "direction": "CallType", "lead_id": "ActionID",
        },
    },
    "helijie": {
        "label": "合力亿捷",
        "enabled": True,
        "webhook_token": "",
        "recording_url_prefix": "",
        "field_map": {
            "phone": "called_no", "recording_url": "record_url",
            "call_duration_sec": "call_duration", "outcome": "call_result",
            "direction": "call_type", "lead_id": "user_field",
        },
    },
}


async def get_config(db: AsyncSession) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    cfg = {**DEFAULTS, "field_map": dict(DEFAULTS["field_map"])}
    if row is not None and isinstance(row.value, dict):
        for k in ("provider", "webhook_token", "auto_transcribe"):
            if k in row.value:
                cfg[k] = row.value[k]
        if isinstance(row.value.get("field_map"), dict):
            cfg["field_map"].update(row.value["field_map"])
        if isinstance(row.value.get("vendors"), dict):
            cfg["vendors"] = {k: dict(v) for k, v in row.value["vendors"].items()
                              if isinstance(v, dict)}
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    val = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    for k in ("provider", "webhook_token", "auto_transcribe"):
        if k in patch:
            val[k] = patch[k]
    if isinstance(patch.get("field_map"), dict):
        val["field_map"] = {**(val.get("field_map") or {}), **patch["field_map"]}
    if isinstance(patch.get("vendors"), dict):
        # 每个 vendor 整体替换;值为 None 表示删除该服务商
        vendors = {k: dict(v) for k, v in (val.get("vendors") or {}).items()}
        for k, v in patch["vendors"].items():
            if v is None:
                vendors.pop(k, None)
            elif isinstance(v, dict):
                vendors[k] = v
        val["vendors"] = vendors
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


async def handle_webhook(db: AsyncSession, *, body: dict, vendor: str | None = None) -> dict:
    """落一条 call 跟进(挂录音)。返回 {matched, lead_id, activity_id, has_recording}。

    vendor:多服务商并行时回调带 ?vendor=key,用该服务商自己的 field_map/录音前缀;
    不带则用顶层 field_map(单服务商兼容)。
    """
    from app.services import sales_analysis_service as ana
    cfg = await get_config(db)
    field_map, rec_prefix, vendor_label = cfg["field_map"], "", None
    if vendor:
        vc = (cfg.get("vendors") or {}).get(vendor)
        if not isinstance(vc, dict) or not vc.get("enabled", True):
            return {"matched": False, "error": f"未知或停用的服务商 {vendor}",
                    "lead_id": None, "activity_id": None, "has_recording": False}
        field_map = vc.get("field_map") or field_map
        rec_prefix = vc.get("recording_url_prefix") or ""
        vendor_label = vc.get("label") or vendor
    p = parse_webhook(body, field_map)
    if p.get("recording_url") and rec_prefix and not str(p["recording_url"]).startswith("http"):
        p["recording_url"] = rec_prefix.rstrip("/") + "/" + str(p["recording_url"]).lstrip("/")
    # direction 列只存 in|out(varchar(4)),服务商话单常给 dialout/callin/呼入 等 → 归一化
    d = str(p.get("direction") or "").lower()
    p["direction"] = "in" if ("in" in d and "dial" not in d) or "呼入" in d else "out"

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
        outcome=str(p["outcome"]) if p.get("outcome") else None,
        content=(f"[{vendor_label}] 呼叫中心话单" if vendor_label else None))
    return {"matched": True, "lead_id": str(lead_id), "activity_id": str(act.id),
            "has_recording": bool(act.recording_url), "vendor": vendor}


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
