"""客服工单（§13.1）：support_tickets · support_messages

用户在线咨询 → 后台客服受理/回复/结案。带存在性保护，可重复 upgrade head。

Revision ID: m66_support_tickets
Revises: m65_content_feedback
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m66_support_tickets"
down_revision = "m65_content_feedback"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    names = _insp().get_table_names()
    if "support_tickets" not in names:
        op.create_table(
            "support_tickets",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("subject", sa.String(120), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="open"),
            sa.Column("last_reply_role", sa.String(10), nullable=True),
            sa.Column("order_id", UUID(as_uuid=True), nullable=True),
            sa.Column("handled_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_support_tickets_user", "support_tickets", ["user_id", "created_at"])
        op.create_index("ix_support_tickets_status", "support_tickets", ["status", "updated_at"])
    if "support_messages" not in names:
        op.create_table(
            "support_messages",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("ticket_id", UUID(as_uuid=True), nullable=False),
            sa.Column("sender_role", sa.String(10), nullable=False),
            sa.Column("sender_id", UUID(as_uuid=True), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_support_messages_ticket", "support_messages", ["ticket_id", "created_at"])


def downgrade() -> None:
    names = _insp().get_table_names()
    if "support_messages" in names:
        op.drop_table("support_messages")
    if "support_tickets" in names:
        op.drop_table("support_tickets")
