"""域23:sales_audit_log(电销 CRM 操作审计)。幂等。

Revision ID: m127_sales_audit_log
Revises: m126_sales_lead_tags
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m127_sales_audit_log"
down_revision = "m126_sales_lead_tags"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "sales_audit_log" in _tables():
        return
    op.create_table(
        "sales_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_sales_audit_lead", "sales_audit_log", ["lead_id", "created_at"])
    op.create_index("ix_sales_audit_admin", "sales_audit_log", ["admin_id", "created_at"])


def downgrade() -> None:
    op.drop_table("sales_audit_log")
