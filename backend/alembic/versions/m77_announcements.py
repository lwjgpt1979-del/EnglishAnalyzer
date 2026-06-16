"""平台公告（§5.6）：announcements

全平台/定向（机构/年级）公告。带存在性保护，可重复 upgrade head。

Revision ID: m77_announcements
Revises: m76_promo_campaigns
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m77_announcements"
down_revision = "m76_promo_campaigns"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "announcements" not in _insp().get_table_names():
        op.create_table(
            "announcements",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("audience", sa.String(12), nullable=False, server_default="all"),
            sa.Column("target_values", JSONB(), nullable=True),
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_announcements_pub", "announcements", ["is_active", "audience"])


def downgrade() -> None:
    if "announcements" in _insp().get_table_names():
        op.drop_table("announcements")
