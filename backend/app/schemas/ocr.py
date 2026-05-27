from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OcrStatusOut(BaseModel):
    """OCR 任务状态（供前端轮询）。"""
    wrong_question_id: uuid.UUID
    ocr_status: str | None           # pending / processing / completed / failed / None
    printed_text: str | None         # 阿里云原始识别结果
    handwritten_text: str | None     # 腾讯云原始识别结果
    error_message: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ConfirmOcrTextRequest(BaseModel):
    """PATCH /wrong-questions/{id}/text 请求体：手动确认/修正 OCR 文字。"""
    question_text: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    question_type: str | None = None
