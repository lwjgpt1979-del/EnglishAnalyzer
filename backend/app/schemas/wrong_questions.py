from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

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
    id: uuid.UUID
    student_id: uuid.UUID
    source_image_url: str
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None
    difficulty: int | None
    tags: list[str] | None
    # KP-First:平台练习/模拟考错题携带内置题面(选项+正确答案+解析),前端直接展示,
    # 无需老图像式「AI 诊断」。source 区分数据源:platform|uploaded|None(=老图片 WrongQuestion)
    options: list | None = None
    explanation: str | None = None
    source: str | None = None
    is_mastered: bool
    mastered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ocr_status: str | None = None
    # SM-2 间隔重复字段（M36）
    review_count: int = 0
    easiness_factor: Decimal = Decimal("2.50")
    review_interval_days: int = 1
    next_review_at: date | None = None
    last_review_at: date | None = None
    # 错题来源 + 回到来源路由 + 已标错因类型(复习卡)
    source_label: str | None = None
    source_route: str | None = None
    error_type: str | None = None

    model_config = {"from_attributes": True}


class WrongQuestionListOut(BaseModel):
    items: list[WrongQuestionOut]
    total: int


class ReviewQueueOut(BaseModel):
    """GET /wrong-questions/review-queue 响应体。"""
    due_items: list[WrongQuestionOut]
    stats: dict  # {total_unmastered, due_today, new_unscheduled}


class RedoIn(BaseModel):
    """POST /wrong-questions/{id}/redo 与 /review 请求体：学生对该错题的重新作答（客观判分）。"""
    user_answer: str = Field(default="", description="重做作答（选项字母或文本），空串按答错处理")


class RedoResultOut(BaseModel):
    """错题重做/复习客观判分结果。"""
    is_correct: bool
    correct_answer: str | None = None
    explanation: str | None = None
    mastered: bool = False           # 本次是否订正/掌握
    next_review_at: date | None = None
    review_count: int = 0


class AiAnalysisOut(BaseModel):
    id: uuid.UUID
    wrong_question_id: uuid.UUID
    llm_provider: str
    error_types: list[str]
    knowledge_points: list[str]
    diagnosis: str
    suggestions: str
    confidence_score: float | None
    tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}
