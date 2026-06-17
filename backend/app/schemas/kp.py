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


# ── R2 平台题 ────────────────────────────────────────────────
class PlatformQuestionItem(BaseModel):
    id: uuid.UUID
    type: str
    parent_real_id: uuid.UUID | None = None
    is_fallback: bool
    question_type: str | None = None
    stem: str | None = None
    answer: str | None = None
    difficulty: int | None = None
    status: str


class PlatformQuestionListOut(BaseModel):
    total: int
    items: list[PlatformQuestionItem]


class GenSimOut(BaseModel):
    generated: int
    sim_ids: list[uuid.UUID]


class ReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published,false=驳回→retired")


# ── R3 错题中心/复习 ──────────────────────────────────────────
import datetime as _dt  # noqa: E402


class WrongReviewItem(BaseModel):
    id: uuid.UUID
    q_scope: str
    question_id: uuid.UUID
    node_id: uuid.UUID | None = None
    review_count: int
    next_review_at: _dt.date | None = None


class WrongReviewQueueOut(BaseModel):
    due_count: int
    items: list[WrongReviewItem]


class WrongReviewSubmitIn(BaseModel):
    wrong_record_id: uuid.UUID
    quality: int = Field(..., ge=0, le=5, description="0-5,SM-2 复习质量")


class WrongReviewSubmitOut(BaseModel):
    status: str
    review_count: int
    next_review_at: _dt.date | None = None


# ── R4 个人知识图谱 ──────────────────────────────────────────
class StudentGraphItem(BaseModel):
    node_id: uuid.UUID
    name: str
    axis: str
    node_kind: str | None = None
    mastery: float | None = None
    practice_count: int
    wrong_count: int
    source_tags: list[str]
    in_scope: bool
    status: str   # mastered|weak|practiced|unlearned


class StudentGraphSummary(BaseModel):
    in_scope: int
    practiced: int
    weak: int
    mastered: int


class StudentGraphOut(BaseModel):
    summary: StudentGraphSummary
    items: list[StudentGraphItem]


class EnrollOut(BaseModel):
    enrolled: int


class StudentTrendPoint(BaseModel):
    date: _dt.date
    accuracy: float
    correct: int
    wrong: int


class StudentTrendOut(BaseModel):
    node_id: uuid.UUID
    points: list[StudentTrendPoint]
