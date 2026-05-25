"""
域8: 用量与报告 (2 张表)
  daily_usage · learning_report_snapshots
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

report_type_enum = sa.Enum("weekly", "monthly", name="report_type")


class DailyUsage(Base):
    """按 (user_id, usage_type, period) 记录每日用量（UPSERT 目标）。"""

    __tablename__ = "daily_usage"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    usage_type = mapped_column(sa.String, nullable=False)
    period = mapped_column(sa.Date, nullable=False)
    count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "usage_type", "period",
            name="uix_daily_usage_identity",
        ),
    )


class LearningReportSnapshot(Base):
    """学情报告快照（每生每周期唯一）。"""

    __tablename__ = "learning_report_snapshots"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    report_type = mapped_column(report_type_enum, nullable=False)
    period_start = mapped_column(sa.Date, nullable=False)
    period_end = mapped_column(sa.Date, nullable=False)
    report_data = mapped_column(JSONB, nullable=False)
    generated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "report_type", "period_start",
            name="uix_learning_report_identity",
        ),
    )
