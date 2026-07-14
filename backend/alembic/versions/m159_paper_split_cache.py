"""paper_split_cache:拆题 LLM 结果按输入文本 md5 缓存(真题按块/按卷复用)。幂等。

Revision ID: m159_paper_split_cache
Revises: m158_kp_classify_cache
Create Date: 2026-07-14
"""
from alembic import op

revision = "m159_paper_split_cache"
down_revision = "m158_kp_classify_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS paper_split_cache (
            input_md5 VARCHAR(32) PRIMARY KEY,
            raw_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS paper_split_cache")
