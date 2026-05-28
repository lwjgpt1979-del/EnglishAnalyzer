"""notifications: add channel/expires_at/meta

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("channel", sa.String(length=20), nullable=False, server_default=sa.text("'system'")))
    op.add_column("notifications", sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("meta", JSONB(), nullable=True))
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_column("notifications", "meta")
    op.drop_column("notifications", "expires_at")
    op.drop_column("notifications", "channel")
