"""老师出卷 schemas（D-113）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AssignmentQuestion(BaseModel):
    stem: str
    type: str | None = None
    options: list[str] | None = None
    answer: str | None = None


class AssignmentCreate(BaseModel):
    class_id: uuid.UUID
    title: str = Field(..., min_length=1)
    questions: list[AssignmentQuestion]
    due_at: str | None = None  # ISO


class AssignmentOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str
    questions: list[AssignmentQuestion]
    due_at: str | None = None
    status: str
    published_at: str | None = None
    created_at: str


class AssignmentListItem(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str
    status: str
    due_at: str | None = None
    submission_count: int = 0


class SubmissionItem(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    answers: list | dict
    score: float | None = None
    submitted_at: str


class TeacherAssignmentDetail(BaseModel):
    assignment: AssignmentOut
    submissions: list[SubmissionItem]


class StudentAssignmentItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    due_at: str | None = None
    submitted: bool
    score: float | None = None


class StudentAssignmentDetail(BaseModel):
    assignment: AssignmentOut
    submitted: bool
    answers: list | dict | None = None
    score: float | None = None


class SubmitIn(BaseModel):
    answers: list | dict


class GradeIn(BaseModel):
    score: float = Field(..., ge=0)


class PerQuestionStat(BaseModel):
    index: int
    stem: str
    correct: int
    total: int
    rate: float


class AssignmentStatsOut(BaseModel):
    total_students: int
    submitted_count: int
    completion_rate: float
    graded_count: int
    avg_score: float | None = None
    max_score: float | None = None
    min_score: float | None = None
    per_question: list[PerQuestionStat]


class SuggestOut(BaseModel):
    knowledge_point: str
    questions: list[AssignmentQuestion]
