"""dimension_add_3: content_dimension +vocabulary/reading/translation（保留 dictation）

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-06

content_dimension 同时被 knowledge_point_contents.dimension（教学内容，用 6 维）和
simulated_questions.dimension（仿真题生成，仍用 dictation 听写题）共用。
故只新增 3 个教学维度值，保留 dictation 供仿真题继续使用 → 并集共 7 值。
用 ALTER TYPE ADD VALUE，不改表、不丢数据。
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 12+ 允许在事务内 ADD VALUE（只要本事务内不使用新值）。
    op.execute("ALTER TYPE content_dimension ADD VALUE IF NOT EXISTS 'vocabulary'")
    op.execute("ALTER TYPE content_dimension ADD VALUE IF NOT EXISTS 'reading'")
    op.execute("ALTER TYPE content_dimension ADD VALUE IF NOT EXISTS 'translation'")


def downgrade() -> None:
    # PostgreSQL 不支持从 enum 删除值；保留新增值即可（无害，无数据依赖时也不阻塞回滚）。
    pass
