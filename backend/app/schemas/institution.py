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
    expiring_30d_count: int
    tier_distribution: dict[str, int]
    month_purchase_fen: int


class InviteCodeOut(BaseModel):
    code: str
    expires_at: dt.datetime


class InstitutionTeacherOut(BaseModel):
    id: uuid.UUID
    nickname: str | None = None
    phone: str | None = None
    subject: str | None = None
    cert_status: str
    monthly_paper_quota: int | None = None
    monthly_grading_quota: int | None = None


class TeacherQuotaUpdate(BaseModel):
    monthly_paper_quota: int | None = None
    monthly_grading_quota: int | None = None   # 池内批改/点评子上限（None=随机构池共享）


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
    source: str = "admin"
    created_at: dt.datetime


class ApproveInstitutionRequest(BaseModel):
    admin_username: str


class ApproveInstitutionResult(BaseModel):
    institution_id: uuid.UUID
    admin_username: str
    password: str


class RenewableStudentOut(BaseModel):
    student_id: uuid.UUID
    nickname: str | None = None
    tier: str
    expires_at: dt.datetime


class BatchRenewRequest(BaseModel):
    student_ids: list[uuid.UUID]
    semesters: int = 1          # V2 M26: 续费学期数（1学期 ≈ 183天）
    duration_months: int | None = None  # V1 兼容字段（已废弃，semesters 优先）


class BatchRenewResult(BaseModel):
    renewed_count: int
    total_amount_fen: int
    skipped: list[uuid.UUID]


class BillItemOut(BaseModel):
    date: dt.datetime
    type: str
    summary: str
    amount_fen: int


# ── 机构自助入驻申请（M47，公开免登录）─────────────────────────────────────
class CaptchaOut(BaseModel):
    captcha_id: str
    image_svg: str


class InstitutionApplyCodeRequest(BaseModel):
    phone: str
    captcha_id: str
    captcha_code: str


class InstitutionApplyRequest(BaseModel):
    name: str
    contact_phone: str
    province_code: str
    city_code: str
    address: str
    code: str


class InstitutionApplyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    institution_id: uuid.UUID
    name: str
    status: str
