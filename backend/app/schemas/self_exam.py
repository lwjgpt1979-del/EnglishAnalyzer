"""ProMax 自助出卷 schemas（5C）。"""
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel

from app.schemas.questions import ExamResultOut, PracticeAttemptIn


class SelfExamQuota(BaseModel):
    is_promax: bool
    used: int
    limit: int
    remaining: int


class SelfExamQuestion(BaseModel):
    id: str
    question_type: str
    stem: str
    options: list[str] | None = None
    difficulty: int | None = None


class SelfExamOut(BaseModel):
    """答题页用：含题目快照（不含答案）+ 限时。"""
    id: uuid.UUID
    status: str
    time_limit_sec: int
    weak_kps: list[str] = []
    questions: list[SelfExamQuestion] = []
    total: int | None = None
    correct_count: int | None = None
    accuracy: float | None = None
    created_at: dt.datetime


class SelfExamBrief(BaseModel):
    id: uuid.UUID
    status: str
    total: int | None = None
    correct_count: int | None = None
    accuracy: float | None = None
    created_at: dt.datetime


class SelfExamSubmitIn(BaseModel):
    answers: list[PracticeAttemptIn]


class SelfExamSubmitResult(BaseModel):
    result: ExamResultOut
    exam: SelfExamBrief
