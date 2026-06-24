"""student_ls_review:长难句间隔重现(Leitner 复习盒)。

Revision ID: m111_student_ls_review
Revises: m110_student_ls_state
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m111_student_ls_review"
down_revision = "m110_student_ls_state"
branch_labels = None
depends_on = None


def _has_table(t):
    return sa.inspect(op.get_bind()).has_table(t)


def upgrade():
    if not _has_table("student_ls_review"):
        op.create_table(
            "student_ls_review",
            sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("ls_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("is_student", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("box", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_student_ls_review_due", "student_ls_review", ["user_id", "due_at"])


def downgrade():
    if _has_table("student_ls_review"):
        op.drop_table("student_ls_review")
