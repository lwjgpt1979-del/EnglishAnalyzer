"""vocab_mcq:词汇测试题库(每词 3-5 道混合选择题,LLM 生成全局缓存,随机取用)。幂等。

Revision ID: m180_vocab_mcq
Revises: m179_vocab_word_family
Create Date: 2026-07-19
"""
from alembic import op

revision = "m180_vocab_mcq"
down_revision = "m179_vocab_word_family"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_mcq (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            mcq_type VARCHAR(12) NOT NULL,
            stem TEXT NOT NULL,
            options JSONB NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_mcq_word ON vocab_mcq(word_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_mcq")
