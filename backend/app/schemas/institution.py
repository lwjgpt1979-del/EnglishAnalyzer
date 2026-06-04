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


class PurchaseCreateRequest(BaseModel):
    tier: str
    duration_months: int
    quantity: int


class ActivationCodeOut(BaseModel):
    code: str
    status: str
    used_at: dt.datetime | None = None


class PurchaseOut(BaseModel):
    id: uuid.UUID
    tier: str
    duration_months: int
    quantity: int
    amount_fen: int
    status: str
    created_at: dt.datetime
    codes: list[ActivationCodeOut]


class PurchaseListItem(BaseModel):
    id: uuid.UUID
    tier: str
    duration_months: int
    quantity: int
    amount_fen: int
    status: str
    created_at: dt.datetime
    used_count: int
    total_count: int


class ActivateCodeRequest(BaseModel):
    code: str


class AdminInstitutionCreate(BaseModel):
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str


class AdminInstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str
    status: str
    created_at: dt.datetime


class ApproveInstitutionRequest(BaseModel):
    admin_username: str


class ApproveInstitutionResult(BaseModel):
    institution_id: uuid.UUID
    admin_username: str
    password: str
