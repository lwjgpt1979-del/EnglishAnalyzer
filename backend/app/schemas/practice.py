"""AI 练习模块 Pydantic Schemas。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateQuestionsRequest(BaseModel):
    knowledge_point: str | None = Field(
        None, description="目标知识点；为空则自动选取学生最薄弱知识点"
    )
    count: int = Field(5, ge=1, le=10, description="生成题目数量（1-10）")
    difficulty: int = Field(3, ge=1, le=5, description="难度 1-5")


class PracticeQuestionOut(BaseModel):
    """下发给学生的题目（不含答案与解析，防作弊）。"""

    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    question_type: str
    difficulty: int
    stem: str
    options: list[str]


class SubmitAnswerRequest(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(..., min_length=1, max_length=2000)
    time_spent_sec: int | None = Field(None, ge=0)


class SubmitAnswerResult(BaseModel):
    record_id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool
    correct_answer: str
    explanation: str


class PracticeRecordOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool
    student_answer: str
    practiced_at: datetime
    time_spent_sec: int | None

    model_config = {"from_attributes": True}


class PracticeStatsOut(BaseModel):
    total_practiced: int
    total_correct: int
    correct_rate: float
    by_knowledge_point: dict[str, dict[str, int]]
