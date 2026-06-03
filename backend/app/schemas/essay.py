"""作文精修 schemas（D-109）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class EssayCreate(BaseModel):
    original_text: str = Field(..., min_length=1)
    title: str | None = None
    essay_type: str | None = None
    wrong_question_id: uuid.UUID | None = None


class EssayScoreItem(BaseModel):
    dimension: str
    score: int
    full: int


class EssayIssueItem(BaseModel):
    original: str
    suggestion: str
    type: str
    color: str
    explanation: str


class EssayOut(BaseModel):
    id: uuid.UUID
    original_text: str
    polished_text: str | None = None
    scores: list[EssayScoreItem]
    total: int
    issues: list[EssayIssueItem]
    title: str | None = None
    essay_type: str | None = None
    round_count: int
    status: str
    created_at: str


class EssayListItem(BaseModel):
    id: uuid.UUID
    title: str | None = None
    essay_type: str | None = None
    total: int
    status: str
    created_at: str


class EssayListOut(BaseModel):
    total: int
    items: list[EssayListItem]
