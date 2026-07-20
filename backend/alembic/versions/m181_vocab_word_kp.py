"""vocab_word_kp + vocab_word_relation:单词考点(词根 + 近义/反义/易混/搭配/派生/考法 关系型)。幂等。

Revision ID: m181_vocab_word_kp
Revises: m180_vocab_mcq
Create Date: 2026-07-19
"""
from alembic import op

revision = "m181_vocab_word_kp"
down_revision = "m180_vocab_mcq"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_word_kp (
            word_id UUID PRIMARY KEY REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            root VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_word_relation (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            relation VARCHAR(16) NOT NULL,
            related_word_id UUID REFERENCES vocabulary_words(id) ON DELETE SET NULL,
            related_text TEXT NOT NULL,
            related_zh TEXT,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_vocab_word_relation UNIQUE (word_id, relation, related_text)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_word_relation_word ON vocab_word_relation(word_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_word_relation")
    op.execute("DROP TABLE IF EXISTS vocab_word_kp")
