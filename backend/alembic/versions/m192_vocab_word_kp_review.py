"""考点 AI 自审校(P5):vocab_word_kp.reviewed_at + vocab_word_kp_review 记录表。幂等。

Revision ID: m192_vocab_word_kp_review
Revises: m191_vocab_rel_source
Create Date: 2026-07-20
"""
from alembic import op

revision = "m192_vocab_word_kp_review"
down_revision = "m191_vocab_rel_source"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_word_kp ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ")
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_word_kp_review (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            before JSONB,
            after JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_word_kp_review_word ON vocab_word_kp_review(word_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_word_kp_review")
    op.execute("ALTER TABLE vocab_word_kp DROP COLUMN IF EXISTS reviewed_at")
