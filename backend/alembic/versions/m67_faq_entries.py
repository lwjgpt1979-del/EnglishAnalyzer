"""FAQ 自助模块（§13.2）：faq_entries

后台维护分类 FAQ，小程序「帮助与反馈」自助查询。带存在性保护，可重复 upgrade head。

Revision ID: m67_faq_entries
Revises: m66_support_tickets
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m67_faq_entries"
down_revision = "m66_support_tickets"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "faq_entries" not in _insp().get_table_names():
        op.create_table(
            "faq_entries",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("audience", sa.String(4), nullable=False, server_default="c"),
            sa.Column("category", sa.String(40), nullable=False, server_default="通用"),
            sa.Column("question", sa.String(200), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_faq_entries_pub", "faq_entries", ["is_active", "audience", "sort_order"])


def downgrade() -> None:
    if "faq_entries" in _insp().get_table_names():
        op.drop_table("faq_entries")
