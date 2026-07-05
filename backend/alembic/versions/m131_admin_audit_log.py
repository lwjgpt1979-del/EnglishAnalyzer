"""平台级操作审计表 admin_audit_log(admin 写操作自动留痕,中间件统一记录)。

Revision ID: m131_admin_audit_log
Revises: m130_region_textbook
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m131_admin_audit_log"
down_revision = "m130_region_textbook"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_id", UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("query", sa.String(255), nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_created", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_admin", "admin_audit_log", ["admin_id", "created_at"])
    op.create_index("ix_admin_audit_module", "admin_audit_log", ["module", "created_at"])


def downgrade():
    op.drop_index("ix_admin_audit_module", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_admin", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_created", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
