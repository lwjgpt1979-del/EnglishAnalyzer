"""V2 M28 — 教师出卷相关 schemas。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class SimQuestionOut(BaseModel):
    """仿真题简要信息（老师选题/学生答题用，不含答案）。"""
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    question_type: str
    stem: str
    options: list | None = None
    difficulty: int
    dimension: str | None = None
    model_config = {"from_attributes": True}


class SimQuestionWithAnswerOut(SimQuestionOut):
    """仿真题含答案版（老师预览 / 批改用）。"""
    answer: str
    explanation: str | None = None


class SimQuestionListOut(BaseModel):
    items: list[SimQuestionOut]
    total: int


class ClassPaperCreate(BaseModel):
    """POST /teacher/classes/{id}/papers 请求体。"""
    title: str
    textbook_version: str | None = None
    grade: str | None = None
    semester: str | None = None
    description: str | None = None
    question_ids: list[uuid.UUID] = []


class ClassPaperOut(BaseModel):
    """班级卷子摘要（老师/学生列表用）。"""
    paper_id: uuid.UUID
    class_id: uuid.UUID
    title: str
    textbook_version: str | None = None
    grade: str | None = None
    semester: str | None = None
    description: str | None = None
    question_count: int = 0
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ClassPaperDetailOut(ClassPaperOut):
    """班级卷子详情（含题目列表）。"""
    questions: list[SimQuestionOut] = []
