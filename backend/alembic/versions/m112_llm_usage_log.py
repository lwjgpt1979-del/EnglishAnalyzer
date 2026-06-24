"""llm_usage_log:LLM 调用用量台账(token/模型/用途),供后台看用量与成本。

Revision ID: m112_llm_usage_log
Revises: m111_student_ls_review
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m112_llm_usage_log"
down_revision = "m111_student_ls_review"
branch_labels = None
depends_on = None


def _has_table(t):
    return sa.inspect(op.get_bind()).has_table(t)


def upgrade():
    if not _has_table("llm_usage_log"):
        op.create_table(
            "llm_usage_log",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("feature", sa.String(32), nullable=False, server_default=sa.text("'other'")),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("finish_reason", sa.String(16), nullable=True),
        )
        op.create_index("ix_llm_usage_created", "llm_usage_log", ["created_at"])
        op.create_index("ix_llm_usage_feature", "llm_usage_log", ["feature"])


def downgrade():
    if _has_table("llm_usage_log"):
        op.drop_table("llm_usage_log")
