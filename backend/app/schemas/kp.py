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


# ── R5 通用词库(admin) ───────────────────────────────────────
class VocabListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    exam_level: str | None = None
    source_type: str | None = None
    status: str = "draft"


class VocabListOut(BaseModel):
    id: uuid.UUID
    name: str
    exam_level: str | None = None
    source_type: str | None = None
    status: str


class VocabListsOut(BaseModel):
    items: list[VocabListOut]


class VocabItemIn(BaseModel):
    word: str | None = None
    word_id: uuid.UUID | None = None
    rank: int | None = None
    frequency: int | None = None
    star: int = 0
    verified: bool = False


class VocabItemsIn(BaseModel):
    items: list[VocabItemIn] = Field(..., min_length=1)


class VocabItemOut(BaseModel):
    word_id: uuid.UUID
    word: str
    rank: int | None = None
    frequency: int | None = None
    star: int
    verified: bool


class VocabItemsOut(BaseModel):
    total: int
    items: list[VocabItemOut]


# ── R6 知识节点资源 ──────────────────────────────────────────
class NodeResourceItem(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    resource_type: str
    dimension: str | None = None
    title: str | None = None
    content_md: str | None = None
    media_url: str | None = None
    resource_json: object | None = None
    status: str


class NodeResourceListOut(BaseModel):
    total: int
    items: list[NodeResourceItem]


class AddResourceIn(BaseModel):
    node_id: uuid.UUID
    resource_type: str = Field(..., description="lecture|video|example|essay|mindmap")
    dimension: str | None = Field(None, description="仅 lecture:听/词汇/语法/阅读/翻译/写作")
    title: str | None = None
    content_md: str | None = None
    media_url: str | None = None
    resource_json: object | None = None
    status: str = "draft"


class UpdateResourceIn(BaseModel):
    content_md: str | None = None
    media_url: str | None = None
    title: str | None = None
    resource_json: object | None = None


# ── 长难句(学生端) ──────────────────────────────────────────
class LongSentenceNodeRef(BaseModel):
    node_id: uuid.UUID
    name: str
    node_kind: str | None = None


class LongSentenceItem(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    syntax_points: list[str] = []


class LongSentenceListOut(BaseModel):
    total: int
    items: list[LongSentenceItem]


class LongSentenceDetailOut(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    analysis: dict | None = None      # main_clause/layers/translation/difficulty_points/syntax_points
    nodes: list[LongSentenceNodeRef] = []   # 句法点 → 跳 /curriculum/nodes/{node_id}/resources


class VerifyTypesOut(BaseModel):
    types: list[str]                  # 已开放(且本期可用)的验证题型,学生自选


class VerifyQuestionOut(BaseModel):
    type: str
    prompt: str
    options: list[str]                # 不含答案


class VerifySubmitIn(BaseModel):
    type: str
    answer: str = Field(..., min_length=1)


class VerifySubmitOut(BaseModel):
    correct: bool
    correct_answer: str
    mastered_nodes: list[str] = []    # 本次达标判掌握的句法点
