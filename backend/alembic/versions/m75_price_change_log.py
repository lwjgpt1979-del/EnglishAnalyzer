"""定价变更历史存档（§5.7）：price_change_logs

每次改定价存快照，用于退款/争议举证。带存在性保护，可重复 upgrade head。

Revision ID: m75_price_change_log
Revises: m74_teacher_cert_review
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m75_price_change_log"
down_revision = "m74_teacher_cert_review"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "price_change_logs" not in _insp().get_table_names():
        op.create_table(
            "price_change_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("config_key", sa.String(40), nullable=False),
            sa.Column("snapshot", JSONB(), nullable=False),
            sa.Column("changed_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_price_change_logs_key", "price_change_logs", ["config_key", "created_at"])


def downgrade() -> None:
    if "price_change_logs" in _insp().get_table_names():
        op.drop_table("price_change_logs")
