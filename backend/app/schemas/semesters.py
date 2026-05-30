"""V2 学期相关 Schemas（D-079 / M1）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SemesterPricing(BaseModel):
    basic: int   # 元/学期
    pro: int
    promax: int


class SemesterIdentity(BaseModel):
    """一个学期的标识（教材+年级+上/下）。"""
    textbook_version: str
    grade: str
    semester: Literal["上", "下"]


class PurchaseSemestersRequest(BaseModel):
    tier: Literal["basic", "pro", "promax"]
    semesters: list[SemesterIdentity] = Field(..., min_length=1, max_length=12)
    target_student_id: uuid.UUID | None = None


class PurchasedSemesterOut(BaseModel):
    id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    tier: str
    started_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class SemesterAccessOut(BaseModel):
    textbook_version: str
    grade: str
    semester: str
    accessible: bool
    tier: str | None
    expires_at: datetime | None
