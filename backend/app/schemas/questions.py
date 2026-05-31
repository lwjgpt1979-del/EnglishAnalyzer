"""V2 仿真题 + 练习 Pydantic schemas（D-079 / M3a）。"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


# ─── AI 生成输出（question_ai_service → question_service.persist）─

class AIGeneratedQuestion(BaseModel):
    question_type: Literal["单选", "填空", "判断"]
    stem: str = Field(..., min_length=5, description="题干文本")
    options: list[str] | None = Field(
        None, description="单选题为 4 个选项字符串；填空/判断为 null"
    )
    answer: str = Field(..., min_length=1, description="单选: A-D；填空: 答案 或 多候选用 | 分隔；判断: 对/错")
    explanation: str = Field(..., min_length=10, description="解析")
    difficulty: int = Field(..., ge=1, le=5)


# ─── API 响应/请求 ─────────────────────────────────────────────────────────

class SimQuestionOut(BaseModel):
    """前端拿到的题目（不带 answer 防作弊）。"""
    id: uuid.UUID
    question_type: str
    stem: str
    options: list[str] | None = None
    difficulty: int


class PracticeAttemptIn(BaseModel):
    question_id: uuid.UUID
    user_answer: str = Field(..., min_length=1, max_length=500)


class PracticeResultOut(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str
    wrong_question_id: uuid.UUID | None = Field(
        None, description="做错时自动落 wrong_questions 表，返回 id 方便前端跳错题详情"
    )
