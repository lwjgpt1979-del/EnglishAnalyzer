"""阅读表达批改 schema（P2a）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ReadingExpressionGradeIn(BaseModel):
    """一道阅读表达简答的批改请求。"""
    question: str = Field(..., min_length=1, description="题目/问题")
    reference_answer: str = Field(..., min_length=1, description="参考答案")
    student_answer: str = Field("", description="学生作答(空则返回未作答)")
    passage: str | None = Field(None, description="所属短文(可选,判分参考)")
    full_score: int = Field(4, ge=1, le=20, description="本题满分")
