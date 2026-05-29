"""班级相关 Schemas（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ClassCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class ClassOut(BaseModel):
    id: uuid.UUID
    name: str
    student_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ClassStudentAddRequest(BaseModel):
    student_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


class ClassStudentOut(BaseModel):
    student_id: uuid.UUID
    joined_at: datetime

    model_config = {"from_attributes": True}
