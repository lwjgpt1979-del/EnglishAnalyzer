"""教师端 Pydantic Schemas。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BecomeTeacherRequest(BaseModel):
    subject: str | None = Field(None, description="任教科目，如'英语'")


class TeacherProfileOut(BaseModel):
    user_id: uuid.UUID
    subject: str | None
    cert_status: str
    cert_doc_url: str | None = None
    max_students: int

    model_config = {"from_attributes": True}


class InviteCodeOut(BaseModel):
    code: str
    expires_at: datetime


class BindTeacherRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="6位邀请码")


class TeacherStudentOut(BaseModel):
    student_id: uuid.UUID
    bound_at: datetime | None

    model_config = {"from_attributes": True}


class TeacherCommentCreate(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=2000)


class TeacherCommentOut(BaseModel):
    id: uuid.UUID
    wrong_question_id: uuid.UUID
    teacher_id: uuid.UUID
    comment_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CertSubmitRequest(BaseModel):
    cert_doc_url: str = Field(..., min_length=1, description="证书文档 URL（已上传至 COS）")


class CertReviewRequest(BaseModel):
    approve: bool
    reason: str | None = Field(None, description="拒绝时填理由")


class QRCodeOut(BaseModel):
    code: str
    expires_at: datetime
    qrcode_base64: str = Field(..., description="PNG/JPEG base64，前端用 data: 前缀展示")


class SendInviteSmsRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)


class SendInviteSmsOut(BaseModel):
    sent: bool
    code: str
