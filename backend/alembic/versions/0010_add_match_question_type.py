"""add 连线 to ai_question_type enum (M3b)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-01

PostgreSQL: ALTER TYPE ... ADD VALUE must run outside a transaction.
We explicitly COMMIT the implicit alembic transaction before issuing
the ADD VALUE so PG accepts it.
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE ai_question_type ADD VALUE IF NOT EXISTS '连线'")


def downgrade() -> None:
    pass
