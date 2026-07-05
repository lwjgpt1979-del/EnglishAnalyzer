"""users.admin_modules —— 管理员模块权限(RBAC)。

NULL=全权超管(存量管理员不受影响);非空 JSONB 数组=子管理员仅可访问所列模块。

Revision ID: m132_users_admin_modules
Revises: m131_admin_audit_log
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m132_users_admin_modules"
down_revision = "m131_admin_audit_log"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("admin_modules", JSONB, nullable=True))


def downgrade():
    op.drop_column("users", "admin_modules")
