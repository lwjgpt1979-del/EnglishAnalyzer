"""意见反馈 / BUG 报告（§13.3）：user_feedback

功能建议/BUG（文字+截图）→ 后台汇总队列。带存在性保护，可重复 upgrade head。

Revision ID: m68_user_feedback
Revises: m67_faq_entries
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m68_user_feedback"
down_revision = "m67_faq_entries"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "user_feedback" not in _insp().get_table_names():
        op.create_table(
            "user_feedback",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("kind", sa.String(12), nullable=False, server_default="suggestion"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("images", JSONB(), nullable=True),
            sa.Column("contact", sa.String(60), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("handled_by", UUID(as_uuid=True), nullable=True),
            sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_user_feedback_status", "user_feedback", ["status", "created_at"])


def downgrade() -> None:
    if "user_feedback" in _insp().get_table_names():
        op.drop_table("user_feedback")
