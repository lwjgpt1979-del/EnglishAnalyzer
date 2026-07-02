"""域23 P2:wecom_chat_archive(企微会话存档明文落库)。幂等。

Revision ID: m125_wecom_archive
Revises: m124_sales_crm
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m125_wecom_archive"
down_revision = "m124_sales_crm"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "wecom_chat_archive" in _tables():
        return
    op.create_table(
        "wecom_chat_archive",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger, nullable=True),
        sa.Column("msg_id", sa.String(64), nullable=False),
        sa.Column("from_userid", sa.String(128), nullable=True),
        sa.Column("external_userid", sa.String(128), nullable=True),
        sa.Column("roomid", sa.String(128), nullable=True),
        sa.Column("msgtype", sa.String(16), nullable=False),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column("media_url", sa.String(512), nullable=True),
        sa.Column("msgtime", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=True),
                  sa.ForeignKey("sales_lead.id", ondelete="SET NULL"), nullable=True),
        sa.Column("analyzed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("analysis", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("msg_id", name="uq_wecom_archive_msgid"),
    )
    op.create_index("ix_wecom_archive_external", "wecom_chat_archive", ["external_userid"])
    op.create_index("ix_wecom_archive_lead", "wecom_chat_archive", ["lead_id"])
    op.create_index("ix_wecom_archive_seq", "wecom_chat_archive", ["seq"])


def downgrade() -> None:
    op.drop_table("wecom_chat_archive")
