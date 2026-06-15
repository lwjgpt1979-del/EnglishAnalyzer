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


class FeatureUsage(Base):
    """权益体系：计量功能的配额用量（按用户+能力+周期桶计数）。"""

    __tablename__ = "feature_usage"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    feature_key = mapped_column(sa.String(64), nullable=False)
    period_bucket = mapped_column(sa.String(10), nullable=False)
    count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "feature_key", "period_bucket",
                            name="uix_feature_usage"),
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


class CaptchaChallenge(Base):
    """图形验证码挑战（M48）。

    挡在「发送短信验证码」前，防止脚本盗刷短信。一次性，验证后即核销。
    """

    __tablename__ = "captcha_challenges"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer = mapped_column(sa.String(10), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    consumed = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class UserActivity(Base):
    """行为埋点（§5.5）：每用户每天一条活跃记录，用于 DAU/MAU/活跃趋势。"""

    __tablename__ = "user_activity"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    active_date = mapped_column(sa.Date, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "active_date", name="uix_user_activity"),
    )
