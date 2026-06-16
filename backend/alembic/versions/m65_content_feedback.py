"""内容质量反馈（§5.5）：content_feedback 表

用户上报"诊断有误/题目有误" → 后台处理；大盘据此算反馈率，监控 AI/题库质量。
带存在性保护，可重复 upgrade head。

Revision ID: m65_content_feedback
Revises: m64_user_activity
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m65_content_feedback"
down_revision = "m64_user_activity"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "content_feedback" not in _insp().get_table_names():
        op.create_table(
            "content_feedback",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("target_type", sa.String(), nullable=False),   # diagnosis|question
            sa.Column("target_id", sa.String(), nullable=True),      # 关联对象 id
            sa.Column("snippet", sa.Text(), nullable=True),          # 反馈对象摘要(题干等)
            sa.Column("reason", sa.Text(), nullable=True),           # 用户说明
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),  # pending|handled|dismissed
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("handled_by", UUID(as_uuid=True), nullable=True),
            sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_content_feedback_status", "content_feedback", ["status", "created_at"])
        op.create_index("ix_content_feedback_type", "content_feedback", ["target_type", "created_at"])


def downgrade() -> None:
    if "content_feedback" in _insp().get_table_names():
        op.drop_table("content_feedback")
