"""add weekly_report to notification_type enum (V2 M30)

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-09
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'weekly_report'")


def downgrade() -> None:
    # PG 不支持 REMOVE VALUE，降级时保留枚举值（不影响功能）
    pass
