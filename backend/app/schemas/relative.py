"""亲人端 Schemas（D-076 / P0 亲人端）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class RelativeInviteCodeOut(BaseModel):
    code: str
    expires_at: datetime


class BindRelativeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    relationship: str = Field(..., min_length=1, max_length=16)


class StudentRelativeOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    relative_id: uuid.UUID
    relationship: str
    is_active: bool
    bound_at: datetime

    model_config = {"from_attributes": True}


class BoundStudentOut(BaseModel):
    student_id: uuid.UUID
    relationship: str
    bound_at: datetime
