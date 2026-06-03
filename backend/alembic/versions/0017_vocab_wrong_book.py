"""vocab wrong book: is_wrong / wrong_count on vocabulary_learning (词力通错词本)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocabulary_learning", sa.Column(
        "is_wrong", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("vocabulary_learning", sa.Column(
        "wrong_count", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("vocabulary_learning", "wrong_count")
    op.drop_column("vocabulary_learning", "is_wrong")
