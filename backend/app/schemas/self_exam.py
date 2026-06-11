"""ProMax 自助出卷 schemas（5C）。"""
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class SelfExamQuota(BaseModel):
    is_promax: bool
    used: int
    limit: int
    remaining: int


class SelfExamQuestion(BaseModel):
    id: str
    section: str = "objective"          # listening / objective / writing
    question_type: str
    stem: str
    options: list[str] | None = None
    difficulty: int | None = None
    audio_text: str | None = None        # 听力区：朗读文本（前端经 /tts 合成音频）


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


class SelfExamAnswerIn(BaseModel):
    question_id: str          # 可为 simulated_question UUID 或 听力/写作的合成 id
    user_answer: str = ""


class SelfExamSubmitIn(BaseModel):
    answers: list[SelfExamAnswerIn]


class SelfExamItemResult(BaseModel):
    id: str
    section: str
    stem: str
    correct: bool | None = None          # 写作题为 None（不计正误）
    correct_answer: str = ""
    user_answer: str = ""
    explanation: str = ""


class SelfExamResult(BaseModel):
    total: int                            # 计分题数（听力+客观）
    correct_count: int
    items: list[SelfExamItemResult]
    writing_submitted: bool = False
    writing_prompt: str = ""
    writing_text: str = ""


class SelfExamSubmitResult(BaseModel):
    result: SelfExamResult
    exam: SelfExamBrief
