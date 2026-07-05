"""system_configs.updated_by 改可空 —— 自动流程(地图获客用量计数)无操作人。

map_usage_service.bump 幂等建/更新 map_fetch 配置行时没有 admin,而 updated_by NOT NULL
导致 NotNullViolation → 高德/百度检索 500。放开非空即可(有操作人时仍会写)。

Revision ID: m128_sysconfig_updated_by_nullable
Revises: m127_sales_audit_log
Create Date: 2026-07-05
"""
from alembic import op

revision = "m128_sysconfig_upby_null"
down_revision = "m127_sales_audit_log"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE system_configs ALTER COLUMN updated_by DROP NOT NULL")


def downgrade():
    op.execute("ALTER TABLE system_configs ALTER COLUMN updated_by SET NOT NULL")
