from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── 请求体 ────────────────────────────────────────────────────────────────────


class WrongQuestionCreate(BaseModel):
    """POST /wrong-questions/ 请求体。"""

    source_image_url: str = Field(..., description="已上传的题目图片 URL（必填）")
    question_text: str | None = Field(None, description="题目文字（OCR 结果或手动录入）")
    student_answer: str | None = Field(None, description="学生作答")
    correct_answer: str | None = Field(None, description="正确答案")
    question_type: str | None = Field(
        None,
        description="题型：单选 | 完型 | 阅读 | 作文 | 其他",
    )
    difficulty: int | None = Field(None, ge=1, le=5, description="难度 1-5")
    tags: list[str] | None = Field(None, description="自定义标签列表")


class MarkMasteredRequest(BaseModel):
    """PATCH /wrong-questions/{id}/mastered 请求体。"""

    is_mastered: bool


# ── 响应体 ────────────────────────────────────────────────────────────────────


class WrongQuestionOut(BaseModel):
    id: str
    student_id: str
    source_image_url: str
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None
    difficulty: int | None
    tags: list[str] | None
    is_mastered: bool
    mastered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WrongQuestionListOut(BaseModel):
    items: list[WrongQuestionOut]
    total: int


class AiAnalysisOut(BaseModel):
    id: str
    wrong_question_id: str
    llm_provider: str
    error_types: list[str]
    knowledge_points: list[str]
    diagnosis: str
    suggestions: str
    confidence_score: float | None
    tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}
