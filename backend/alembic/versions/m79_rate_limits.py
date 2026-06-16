"""限流计数（上线硬化）：rate_limits

固定窗口防爆破计数表。带存在性保护，可重复 upgrade head。

Revision ID: m79_rate_limits
Revises: m78_teacher_grading_quota
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m79_rate_limits"
down_revision = "m78_teacher_grading_quota"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "rate_limits" not in _insp().get_table_names():
        op.create_table(
            "rate_limits",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("bucket_key", sa.String(160), nullable=False),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("bucket_key", "window_start", name="uix_rate_limits"),
        )
        op.create_index("ix_rate_limits_window", "rate_limits", ["window_start"])


def downgrade() -> None:
    if "rate_limits" in _insp().get_table_names():
        op.drop_table("rate_limits")
