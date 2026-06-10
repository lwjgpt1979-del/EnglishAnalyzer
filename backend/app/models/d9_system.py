"""
域9: 系统配置与通知 (2 张表)
  system_configs · notifications
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

notification_type_enum = sa.Enum(
    "system",
    "membership",
    "assignment",
    "analysis_done",
    "report_ready",
    "bind_request",
    "bind_accepted",
    "bind_rejected",
    "ocr_failed",
    "checkin_reminder",
    "weekly_report",
    name="notification_type",
)


class SystemConfig(Base):
    """系统参数键值对（JSONB 值，支持任意结构）。"""

    __tablename__ = "system_configs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = mapped_column(sa.String, nullable=False, unique=True)
    value = mapped_column(JSONB, nullable=False)
    description = mapped_column(sa.Text, nullable=True)
    updated_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Notification(Base):
    """站内通知（G15: 补充 read_at）。"""

    __tablename__ = "notifications"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    type = mapped_column(notification_type_enum, nullable=False)
    title = mapped_column(sa.String, nullable=False)
    content = mapped_column(sa.Text, nullable=False)
    channel = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'system'"))
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    meta = mapped_column(JSONB, nullable=True)
    is_read = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    # G15: is_read=true 时同步写入 read_at，便于统计消息响应时长
    read_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SmsVerification(Base):
    """通用短信验证码（M47）。

    服务于尚无账号的申请人按 (phone, purpose) 验证手机号，例如机构自助入驻申请。
    已登录用户的验证码仍存在 users.phone_verify_code。
    """

    __tablename__ = "sms_verifications"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = mapped_column(sa.String(20), nullable=False)
    purpose = mapped_column(sa.String(40), nullable=False)
    code = mapped_column(sa.String(6), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    consumed = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
