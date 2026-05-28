"""合规相关 Schemas：年龄核验 + 协议确认 + 账号注销。"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

CURRENT_AGREEMENT_VERSION = "v1.0"


class CompleteProfileRequest(BaseModel):
    birth_year: int = Field(..., ge=1900, le=2030, description="出生年份")
    guardian_phone: str | None = Field(None, min_length=11, max_length=20, description="<14岁必填监护人手机号")
    user_phone: str | None = Field(None, min_length=11, max_length=20, description="可选，用户本人手机号，注销时验证用")
    agreement_version: str = Field(..., description="同意的协议版本（当前 v1.0）")


class CompleteProfileResponse(BaseModel):
    profile_completed: bool
    needs_guardian_verify: bool
    age: int


class GuardianVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class CancelAccountConfirm(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class CancellationStatusOut(BaseModel):
    requested_at: datetime | None
    scheduled_at: datetime | None
    days_remaining: int | None
