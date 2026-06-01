"""add dimension to simulated_questions (维度感知练习题)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# 复用迁移 0007 已创建的 content_dimension 枚举，绝不重建类型
_dimension = postgresql.ENUM(
    "listening", "dictation", "grammar", "writing",
    name="content_dimension", create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "simulated_questions",
        sa.Column("dimension", _dimension, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulated_questions", "dimension")
