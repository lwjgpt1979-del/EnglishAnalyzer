"""V2 整卷上传 OCR 拆题 Pydantic schemas（D-089 / M4）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserPaperCreate(BaseModel):
    """学生提交整卷：一张或多张试卷图片 URL（已通过 upload 预签名上传到 COS）。"""
    source_image_urls: list[str] = Field(..., min_length=1, max_length=20)
    title: str | None = Field(None, max_length=100)


class UserPaperQuestionOut(BaseModel):
    """拆出来的单题。"""
    id: uuid.UUID
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None
    is_wrong: bool


class UserPaperOut(BaseModel):
    """试卷概要（列表用）。"""
    id: uuid.UUID
    title: str | None
    source_image_urls: list[str]
    ocr_status: str | None
    question_count: int
    created_at: datetime


class UserPaperDetailOut(UserPaperOut):
    """试卷详情：概要 + 拆出的题目列表。"""
    questions: list[UserPaperQuestionOut]


class UserPaperListOut(BaseModel):
    items: list[UserPaperOut]
    total: int
