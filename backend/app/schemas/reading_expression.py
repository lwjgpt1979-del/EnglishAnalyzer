"""阅读表达批改 schema（P2a）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ReadingExpressionGradeIn(BaseModel):
    """一道阅读表达简答的批改请求。"""
    question: str = Field(..., min_length=1, description="题目/问题")
    reference_answer: str = Field(..., min_length=1, description="参考答案")
    student_answer: str = Field("", description="学生作答(空则返回未作答)")
    passage: str | None = Field(None, description="所属短文(可选,判分参考)")
    full_score: int = Field(4, ge=1, le=20, description="本题满分")


class ReadingExpressionGradeByQuestionIn(BaseModel):
    """按 question_id 批改(参考答案服务端取,防作弊)+ 落 KP 错题闭环。"""
    question_id: uuid.UUID = Field(..., description="平台阅读表达题 id")
    student_answer: str = Field("", description="学生作答")
    full_score: int = Field(4, ge=1, le=20, description="本题满分")
