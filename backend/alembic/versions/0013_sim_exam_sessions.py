"""create sim_exam_sessions (模拟考成绩历史)

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_exam_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sim_exam_sessions_student_id", "sim_exam_sessions", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_sim_exam_sessions_student_id", table_name="sim_exam_sessions")
    op.drop_table("sim_exam_sessions")
