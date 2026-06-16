"""V2 学期相关 Schemas（D-079 / M1）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SemesterPricing(BaseModel):
    basic: int   # 元/学期（实售价）
    pro: int
    promax: int
    # 划线价（原价，元/学期；0/缺省=不展示，§5.7）
    list_basic: int = 0
    list_pro: int = 0
    list_promax: int = 0


class SemesterPricingUpdate(BaseModel):
    """运营改定价请求（M5）：三档单价必须为正整数；划线价可选。"""
    basic: int = Field(..., ge=1, description="basic 档单价（元/学期）")
    pro: int = Field(..., ge=1, description="pro 档单价（元/学期）")
    promax: int = Field(..., ge=1, description="promax 档单价（元/学期）")
    list_basic: int = Field(0, ge=0, description="basic 划线价（元/学期，0=不展示）")
    list_pro: int = Field(0, ge=0, description="pro 划线价")
    list_promax: int = Field(0, ge=0, description="promax 划线价")


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
