"""机构后台 schemas（D-120）。"""
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class InstitutionProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str
    status: str
    created_at: dt.datetime


class InstitutionProfileUpdate(BaseModel):
    name: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class InstitutionOverviewOut(BaseModel):
    teacher_count: int
    student_count: int
    member_count: int
    active_7d_count: int


class InviteCodeOut(BaseModel):
    code: str
    expires_at: dt.datetime


class InstitutionTeacherOut(BaseModel):
    id: uuid.UUID
    nickname: str | None = None
    phone: str | None = None
    subject: str | None = None
    cert_status: str


class JoinInstitutionRequest(BaseModel):
    code: str
