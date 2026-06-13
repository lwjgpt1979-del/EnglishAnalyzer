"""vocabulary_words 加 phrases 列（词力通词卡：短语）

Revision ID: m53_vocab_phrases
Revises: m52_speaking
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m53_vocab_phrases"
down_revision = "m52_speaking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocabulary_words", sa.Column("phrases", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("vocabulary_words", "phrases")
