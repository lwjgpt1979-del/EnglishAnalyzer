"""student_ls_state:学生长难句自适应水平 θ(随反馈持续校准)。

Revision ID: m110_student_ls_state
Revises: m109_ls_locate_student
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m110_student_ls_state"
down_revision = "m109_ls_locate_student"
branch_labels = None
depends_on = None


def _has_table(t):
    return sa.inspect(op.get_bind()).has_table(t)


def upgrade():
    if not _has_table("student_ls_state"):
        op.create_table(
            "student_ls_state",
            sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("theta", sa.Numeric(5, 2), nullable=False),
            sa.Column("seen_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade():
    if _has_table("student_ls_state"):
        op.drop_table("student_ls_state")
