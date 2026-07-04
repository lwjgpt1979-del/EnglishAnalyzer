"""阿里云呼叫中心 CCC 接入(拉取中转):通话结束(contactId)→ 调 CCC 通话记录 API 拿录音 URL/被叫号
→ 按被叫号匹配线索 → 落 call 跟进(挂录音)→ 触发腾讯 ASR + 意向分析。

为什么是「拉」不是「推」:阿里云 CCC 通话结束事件里通常只给 contactId,录音存阿里云 OSS,
要用 AccessKey 再调通话记录 API 拿录音地址。故本服务负责「按 contactId 拉详情」这一步。

dev-mock:未配 CCC AccessKey(settings.aliyun_ccc_access_key_id 仍是 placeholder)时,
_fetch_contact 返回模拟详情,整条链路(匹配→落库→ASR→分析)可离线自测;配真 AK 即走真 API。

真路径用**通用 OpenAPI 客户端**(alibabacloud_tea_openapi):action / api_version / endpoint / 字段路径
全走 system_configs.aliyun_ccc 配置——不同实例/版本只改配置不改码。
⚠️ 上线前务必用你实例真实的「通话记录」接口名 + 一条真实响应,校准 action_get_contact 与 field_map。
"""
from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.d9_system import SystemConfig
from app.models.d23_sales_crm import SalesLead

_log = logging.getLogger(__name__)
_KEY = "aliyun_ccc"

DEFAULTS: dict = {
    "instance_id": "",                       # CCC 实例 ID
    "region_id": "cn-shanghai",
    "endpoint": "ccc.cn-shanghai.aliyuncs.com",
    "api_version": "2020-07-01",             # ⚠️ 以你实例的 OpenAPI 版本为准
    "action_get_contact": "GetConversationDetailByContactId",  # ⚠️ 以真实接口名为准
    "auto_transcribe": True,
    "mock_recording_url": "",                # 仅 dev-mock 联调:填公网录音 URL,让模拟 contact 带录音一路跑到真 ASR
    # CCC 响应 → 内部字段的取值路径(点分,支持数字下标取列表)。⚠️ 按真实响应校准
    "field_map": {
        "phone": "CallingNumber",            # 客户号(外呼时客户是被叫;回记录里字段名以实测为准)
        "recording_url": "RecordingList.0.OssLink",
        "call_duration_sec": "TalkTime",
        "outcome": "Status",
    },
}


def is_dev_mock() -> bool:
    """未配真 CCC AccessKey、或未装通用 OpenAPI 客户端 → dev-mock。"""
    if (settings.aliyun_ccc_access_key_id or "").startswith("placeholder"):
        return True
    try:
        import alibabacloud_tea_openapi  # noqa: F401
        return False
    except ImportError:
        return True


async def get_config(db: AsyncSession) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    cfg = {**DEFAULTS, "field_map": dict(DEFAULTS["field_map"])}
    if row is not None and isinstance(row.value, dict):
        for k in DEFAULTS:
            if k == "field_map":
                continue
            if k in row.value:
                cfg[k] = row.value[k]
        if isinstance(row.value.get("field_map"), dict):
            cfg["field_map"].update(row.value["field_map"])
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    val = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    for k in DEFAULTS:
        if k == "field_map":
            continue
        if k in patch:
            val[k] = patch[k]
    if isinstance(patch.get("field_map"), dict):
        val["field_map"] = {**(val.get("field_map") or {}), **patch["field_map"]}
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=val,
                            description="阿里云呼叫中心 CCC(实例/接口/字段映射)",
                            updated_by=updated_by))
    else:
        row.value = val
        row.updated_by = updated_by
    await db.flush()
    return await get_config(db)


def _dig(obj, path: str):
    """点分路径取值,数字段当列表下标:'RecordingList.0.OssLink'。取不到返回 None。"""
    cur = obj
    for seg in (path or "").split("."):
        if cur is None:
            return None
        if seg.isdigit() and isinstance(cur, (list, tuple)):
            i = int(seg)
            cur = cur[i] if i < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def _extract(resp: dict, field_map: dict) -> dict:
    return {inner: _dig(resp, path) for inner, path in field_map.items()}


def _mock_contact(contact_id: str, mock_recording_url: str = "") -> dict:
    """dev-mock:模拟一条 CCC 通话记录。配了 mock_recording_url 则带录音 → 一路触发真 ASR;否则只验匹配→落库。"""
    return {"phone": "", "recording_url": (mock_recording_url or None),
            "call_duration_sec": 42, "outcome": "connected",
            "_note": f"dev-mock CCC contact {contact_id}"}


def _fetch_contact_sync(contact_id: str, cfg: dict) -> dict:
    """真路径:通用 OpenAPI 客户端调 CCC 通话记录 API → 按 field_map 抽内部字段。"""
    from alibabacloud_tea_openapi.client import Client as OpenApiClient
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_tea_util import models as util_models

    conf = open_api_models.Config(
        access_key_id=settings.aliyun_ccc_access_key_id,
        access_key_secret=settings.aliyun_ccc_access_key_secret,
        endpoint=cfg["endpoint"])
    client = OpenApiClient(conf)
    params = open_api_models.Params(
        action=cfg["action_get_contact"], version=cfg["api_version"],
        protocol="HTTPS", method="POST", auth_type="AK", style="RPC",
        pathname="/", req_body_type="formData", body_type="json")
    req = open_api_models.OpenApiRequest(
        query={"InstanceId": cfg["instance_id"], "ContactId": contact_id})
    resp = client.call_api(params, req, util_models.RuntimeOptions())
    body = (resp or {}).get("body", resp) or {}
    return _extract(body, cfg["field_map"])


async def fetch_and_ingest(db: AsyncSession, *, contact_id: str, phone: str | None = None) -> dict:
    """按 contactId 拉通话详情 → 匹配线索(优先传入 phone,否则用详情里的号)→ 落 call 跟进。

    返回 {matched, lead_id, activity_id, has_recording, dev_mock}。有录音且 auto_transcribe → 后台转写分析。
    """
    from app.services import sales_analysis_service as ana
    from app.services import call_center_service as cc
    cfg = await get_config(db)
    dev = is_dev_mock()
    if dev:
        detail = _mock_contact(contact_id, cfg.get("mock_recording_url") or "")
    else:
        import asyncio
        try:
            detail = await asyncio.to_thread(_fetch_contact_sync, contact_id, cfg)
        except Exception as exc:  # noqa: BLE001
            _log.warning("CCC 拉取通话记录失败 contact=%s: %s", contact_id, exc)
            return {"matched": False, "error": str(exc), "contact_id": contact_id}

    call_phone = (phone or detail.get("phone") or "").strip()
    lead_id = None
    if call_phone:
        lead_id = (await db.execute(sa.select(SalesLead.id)
                   .where(SalesLead.phone == call_phone).limit(1))).scalar_one_or_none()
    if lead_id is None:
        return {"matched": False, "lead_id": None, "activity_id": None,
                "has_recording": False, "dev_mock": dev, "phone": call_phone}

    dur = detail.get("call_duration_sec")
    act = await ana.ingest_call_record(
        db, lead_id=lead_id, admin_id=None,
        recording_url=(str(detail["recording_url"]) if detail.get("recording_url") else None),
        asr_text=None, call_duration_sec=int(dur) if dur else None,
        direction="out", outcome=str(detail["outcome"]) if detail.get("outcome") else None)
    await db.flush()
    if cfg.get("auto_transcribe") and act.recording_url:
        cc.schedule_transcribe(act.id)
    return {"matched": True, "lead_id": str(lead_id), "activity_id": str(act.id),
            "has_recording": bool(act.recording_url), "dev_mock": dev}
