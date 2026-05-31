"""add 判断 to ai_question_type enum (M3a)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-01

PostgreSQL: ALTER TYPE ... ADD VALUE must run outside a transaction.
We explicitly COMMIT the implicit alembic transaction before issuing
the ADD VALUE so PG accepts it.

Downgrade is a no-op — PG doesn't allow enum value removal without
rebuilding the type, and removing 判断 would orphan any rows already
using it.
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE ai_question_type ADD VALUE IF NOT EXISTS '判断'")


def downgrade() -> None:
    pass
