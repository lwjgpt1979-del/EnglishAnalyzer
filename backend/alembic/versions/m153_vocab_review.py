"""vocab_review:词库缺词审核队列(作业/课程缺词→审核入库)。幂等。

Revision ID: m153_vocab_review
Revises: m152_source_paper_id
Create Date: 2026-07-11
"""
from alembic import op

revision = "m153_vocab_review"
down_revision = "m152_source_paper_id"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_review (
            id UUID PRIMARY KEY,
            word_norm VARCHAR(80) NOT NULL UNIQUE,
            word VARCHAR(80) NOT NULL,
            source VARCHAR(16) NOT NULL DEFAULT 'paper',
            occur_count INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_review_status ON vocab_review (status)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_review")
