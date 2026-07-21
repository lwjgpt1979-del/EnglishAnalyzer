"""vocab_word_relation.source:考点项来源(llm | morph 形态学确定性)。幂等。

Revision ID: m191_vocab_word_relation_source
Revises: m190_merge_heads
Create Date: 2026-07-20
"""
from alembic import op

revision = "m191_vocab_rel_source"
down_revision = "m190_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_word_relation ADD COLUMN IF NOT EXISTS source VARCHAR(8) NOT NULL DEFAULT 'llm'")


def downgrade():
    op.execute("ALTER TABLE vocab_word_relation DROP COLUMN IF EXISTS source")
