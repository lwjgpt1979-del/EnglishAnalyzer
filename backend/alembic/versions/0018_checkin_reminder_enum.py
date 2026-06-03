"""add checkin_reminder to notification_type enum (D-108)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-03

PostgreSQL: ALTER TYPE ... ADD VALUE 必须在事务外执行，故先 COMMIT。
Downgrade 为 no-op（PG 不支持删除 enum 值，会孤立已用该值的行）。
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'checkin_reminder'")


def downgrade() -> None:
    pass
