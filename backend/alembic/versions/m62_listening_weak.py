"""听力跟读薄弱句库（§6.4）：listening_shadow_weak 表

跟读得分记录(取最高分)，best_score<60 为薄弱句、下次优先复现。
带存在性保护，可重复 upgrade head。

Revision ID: m62_listening_weak
Revises: m61_invoice_requests
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m62_listening_weak"
down_revision = "m61_invoice_requests"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "listening_shadow_weak" not in _insp().get_table_names():
        op.create_table(
            "listening_shadow_weak",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("sentence", sa.Text(), nullable=False),
            sa.Column("best_score", sa.SmallInteger(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index("uix_listening_shadow_weak", "listening_shadow_weak",
                        ["student_id", "sentence"], unique=True)


def downgrade() -> None:
    if "listening_shadow_weak" in _insp().get_table_names():
        op.drop_table("listening_shadow_weak")
