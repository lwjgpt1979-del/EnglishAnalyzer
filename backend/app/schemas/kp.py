"""KP 候选审核 DTO(R0.4)。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class KpCandidateItem(BaseModel):
    id: uuid.UUID
    raw_name: str
    name_norm: str
    suggested_axis: str | None = None
    suggested_stage: str | None = None
    occur_count: int
    source_type: str | None = None
    context_sample: dict | None = None
    status: str


class KpCandidateListOut(BaseModel):
    total: int
    items: list[KpCandidateItem]


class KpNodeItem(BaseModel):
    id: uuid.UUID
    axis: str
    node_kind: str | None = None
    name: str
    code: str
    applicable_stages: list[str] | None = None


class KpNodeListOut(BaseModel):
    total: int
    items: list[KpNodeItem]


class ApproveCandidateRequest(BaseModel):
    axis: str = Field(..., description="knowledge|ability|exam")
    stage: str | None = Field(None, description="小|初|高;空=全学段通用")
    node_kind: str | None = None
    parent_id: uuid.UUID | None = None


class MergeCandidateRequest(BaseModel):
    target_node_id: uuid.UUID = Field(..., description="把候选名并为该节点的别名")


class RejectCandidateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="驳回理由")


# ── R1 教材接入 ──────────────────────────────────────────────
class UnitNodeItem(BaseModel):
    node_id: uuid.UUID
    name: str
    axis: str
    node_kind: str | None = None
    source: str


class UnitNodeListOut(BaseModel):
    total: int
    items: list[UnitNodeItem]


class UnitExtractOut(BaseModel):
    matched: int
    candidate: int
    edges_created: int
