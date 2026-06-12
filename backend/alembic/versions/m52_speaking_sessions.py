"""speaking_sessions 表（口语练习记录：维度学情 + 打卡）

Revision ID: m52_speaking
Revises: m51_self_exams
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m52_speaking"
down_revision = "m51_self_exams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "speaking_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("scenario_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("missed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("speaking_sessions")
