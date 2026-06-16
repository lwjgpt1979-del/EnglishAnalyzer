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


class ContentFeedback(Base):
    """内容质量反馈（§5.5）：用户上报诊断/题目有误，后台处理。"""

    __tablename__ = "content_feedback"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    target_type = mapped_column(sa.String, nullable=False)   # diagnosis|question
    target_id = mapped_column(sa.String, nullable=True)
    snippet = mapped_column(sa.Text, nullable=True)
    reason = mapped_column(sa.Text, nullable=True)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'pending'"))
    note = mapped_column(sa.Text, nullable=True)
    handled_by = mapped_column(UUID(as_uuid=True), nullable=True)
    handled_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SupportTicket(Base):
    """客服工单（§13.1）：用户在线咨询，后台客服受理/回复/结案。"""

    __tablename__ = "support_tickets"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    category = mapped_column(sa.String(20), nullable=False)   # refund|feature|complaint|order|other
    subject = mapped_column(sa.String(120), nullable=False)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'open'"))  # open|replied|closed
    last_reply_role = mapped_column(sa.String(10), nullable=True)  # user|admin（最后是谁说话）
    order_id = mapped_column(UUID(as_uuid=True), nullable=True)    # 可选关联订单
    handled_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )


class SupportMessage(Base):
    """工单的一条消息（§13.1）。"""

    __tablename__ = "support_messages"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("support_tickets.id"), nullable=False)
    sender_role = mapped_column(sa.String(10), nullable=False)   # user|admin
    sender_id = mapped_column(UUID(as_uuid=True), nullable=True)
    content = mapped_column(sa.Text, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class FaqEntry(Base):
    """FAQ 自助条目（§13.2）：后台维护，小程序「帮助与反馈」展示。"""

    __tablename__ = "faq_entries"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audience = mapped_column(sa.String(4), nullable=False, server_default=sa.text("'c'"))  # c|b|all
    category = mapped_column(sa.String(40), nullable=False, server_default=sa.text("'通用'"))
    question = mapped_column(sa.String(200), nullable=False)
    answer = mapped_column(sa.Text, nullable=False)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    is_active = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    updated_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )


class UserFeedback(Base):
    """意见反馈 / BUG 报告（§13.3）：功能建议/BUG，文字+截图。"""

    __tablename__ = "user_feedback"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    kind = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'suggestion'"))  # suggestion|bug
    content = mapped_column(sa.Text, nullable=False)
    images = mapped_column(JSONB, nullable=True)   # 截图 URL 列表
    contact = mapped_column(sa.String(60), nullable=True)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'pending'"))  # pending|reviewing|done|dismissed
    note = mapped_column(sa.Text, nullable=True)
    handled_by = mapped_column(UUID(as_uuid=True), nullable=True)
    handled_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SensitiveWord(Base):
    """敏感词库（§5.6）：超管动态维护，用于内容过滤（AI报告/作文/老师题目/学生上传）。"""

    __tablename__ = "sensitive_words"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word = mapped_column(sa.String(64), nullable=False, unique=True)
    category = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'other'"))  # political|porn|violence|ad|other
    action = mapped_column(sa.String(10), nullable=False, server_default=sa.text("'block'"))    # block|mask
    is_active = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class PriceChangeLog(Base):
    """定价变更历史存档（§5.7）：每次改定价存一份快照，用于退款/争议举证。"""

    __tablename__ = "price_change_logs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = mapped_column(sa.String(40), nullable=False)   # 如 semester_pricing
    snapshot = mapped_column(JSONB, nullable=False)             # 改后完整定价快照
    changed_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class Announcement(Base):
    """平台公告（§5.6）：全平台或定向（机构/年级）发布。

    audience: all(全平台) | institution(指定机构) | grade(指定年级)。
    target_values: audience 为 institution/grade 时的目标值列表（机构 id 串 / 年级名）。
    starts_at/ends_at 为空表示不限；展示按 is_active + 时间窗 + 受众匹配。
    """

    __tablename__ = "announcements"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = mapped_column(sa.String(120), nullable=False)
    content = mapped_column(sa.Text, nullable=False)
    audience = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'all'"))
    target_values = mapped_column(JSONB, nullable=True)   # [institution_id...] 或 [grade...]
    pinned = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    starts_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    ends_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_active = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
