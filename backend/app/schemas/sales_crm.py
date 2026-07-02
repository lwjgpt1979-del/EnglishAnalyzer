"""电销 CRM 请求/响应 schema(P0)。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SalesLeadCreate(BaseModel):
    name: str
    contact_name: str | None = None
    phone: str | None = None
    wechat_id: str | None = None
    address: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    industry: str | None = None
    biz_tags: list[str] | None = None
    source: str | None = None
    source_note: str | None = None
    consent: bool | None = None
    dnc: bool | None = None


class SalesLeadUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    wechat_id: str | None = None
    address: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    industry: str | None = None
    biz_tags: list[str] | None = None
    source_note: str | None = None
    status: str | None = None
    consent: bool | None = None
    dnc: bool | None = None
    next_follow_at: datetime | None = None
    intent_score: int | None = None
    intent_grade: str | None = None


class SalesLeadImport(BaseModel):
    items: list[SalesLeadCreate]
    source: str = "import"


class ActivityCreate(BaseModel):
    channel: str                      # call|wechat|note|sms
    content: str | None = None
    direction: str | None = None      # out|in
    outcome: str | None = None        # connected|no_answer|rejected|callback…
    next_follow_at: datetime | None = None
    status: str | None = None         # 顺带推进线索状态


class CallRecordIn(BaseModel):
    """呼叫中心接入位:一通电话的录音/转写回传。"""
    recording_url: str | None = None
    asr_text: str | None = None
    call_duration_sec: int | None = None
    direction: str | None = "out"
    outcome: str | None = None
    content: str | None = None


class AnalyzeTextIn(BaseModel):
    text: str
    source: str = "call"


class WecomMsgIn(BaseModel):
    """已解密的一条企微会话消息(接入位:真·puller 或回调解密后喂入)。"""
    msg_id: str
    seq: int | None = None
    from_userid: str | None = None
    external_userid: str | None = None
    roomid: str | None = None
    msgtype: str = "text"
    content_text: str | None = None
    media_url: str | None = None
    msgtime: int | str | None = None      # 毫秒时间戳 / ISO


class WecomIngestIn(BaseModel):
    items: list[WecomMsgIn]
    run_analysis: bool = True


class WecomConfigUpdate(BaseModel):
    enabled: bool | None = None
    corp_id: str | None = None
    last_seq: int | None = None
    analyze_window: int | None = None


class WecomMsgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seq: int | None
    msg_id: str
    from_userid: str | None
    external_userid: str | None
    roomid: str | None
    msgtype: str
    content_text: str | None
    media_url: str | None
    msgtime: datetime | None
    lead_id: uuid.UUID | None
    analyzed: bool
    analysis: Any | None
    created_at: datetime


class SalesLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    wechat_id: str | None
    address: str | None
    region_code: str | None
    region_name: str | None
    industry: str | None
    biz_tags: Any | None
    source: str
    source_note: str | None
    status: str
    intent_score: int | None
    intent_grade: str | None
    product_feedback: Any | None
    similar_score: float | None
    consent: bool
    dnc: bool
    pool: str
    owner_admin_id: uuid.UUID | None
    claimed_at: datetime | None
    last_contacted_at: datetime | None
    next_follow_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lead_id: uuid.UUID
    admin_id: uuid.UUID | None
    channel: str
    direction: str | None
    content: str | None
    outcome: str | None
    recording_url: str | None
    call_duration_sec: int | None
    asr_text: str | None
    intent_score: int | None
    analysis: Any | None
    created_at: datetime
