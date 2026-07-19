"""vocab_word_family:词族缓存(词根+同族词,LLM 生成全局缓存,G 构词法)。幂等。

Revision ID: m179_vocab_word_family
Revises: m178_user_exam_target
Create Date: 2026-07-19
"""
from alembic import op

revision = "m179_vocab_word_family"
down_revision = "m178_user_exam_target"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_word_family (
            word_id UUID PRIMARY KEY REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            root VARCHAR(64),
            members JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_word_family")
