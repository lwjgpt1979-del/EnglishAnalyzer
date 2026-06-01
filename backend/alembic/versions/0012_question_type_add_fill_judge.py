"""add 填空/判断 to question_type enum

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-01

让 V2 仿真题的填空/判断错题保留原题型，不再降级 "其他"。
PostgreSQL: ALTER TYPE ... ADD VALUE 必须在事务外执行，
故先 COMMIT 掉 alembic 隐式事务再 ADD VALUE。
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS '填空'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS '判断'")


def downgrade() -> None:
    pass
