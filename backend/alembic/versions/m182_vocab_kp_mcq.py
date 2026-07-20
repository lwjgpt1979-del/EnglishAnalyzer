"""vocab_kp_mcq:考点扩展测试题库(按考点维度出题,FK 关联 vocab_word_kp)。幂等。

Revision ID: m182_vocab_kp_mcq
Revises: m181_vocab_word_kp
Create Date: 2026-07-19
"""
from alembic import op

revision = "m182_vocab_kp_mcq"
down_revision = "m181_vocab_word_kp"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_kp_mcq (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocab_word_kp(word_id) ON DELETE CASCADE,
            dimension VARCHAR(16) NOT NULL,
            stem TEXT NOT NULL,
            options JSONB NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_kp_mcq_word ON vocab_kp_mcq(word_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_kp_mcq")
