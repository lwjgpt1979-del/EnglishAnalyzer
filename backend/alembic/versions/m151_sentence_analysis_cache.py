"""sentence_analysis_cache:长难句解析暂存(第三方付费调用不重复付费)。幂等。

Revision ID: m151_sentence_analysis_cache
Revises: m150_paper_image_hash
Create Date: 2026-07-11
"""
from alembic import op

revision = "m151_sentence_analysis_cache"
down_revision = "m150_paper_image_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS sentence_analysis_cache (
            text_hash VARCHAR(32) PRIMARY KEY,
            text TEXT NOT NULL,
            analysis_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS sentence_analysis_cache")
