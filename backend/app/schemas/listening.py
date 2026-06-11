"""听力练习 schemas（听力跟读模块·精听）。"""
from __future__ import annotations

from pydantic import BaseModel


class ListeningBrief(BaseModel):
    id: str
    title: str
    type: str            # dialogue / monologue
    difficulty: int
    question_count: int


class ListeningQuestion(BaseModel):
    prompt: str
    options: list[str]
    answer_index: int
    explanation: str


class ListeningDetail(BaseModel):
    id: str
    title: str
    type: str
    difficulty: int
    transcript: str
    questions: list[ListeningQuestion]
