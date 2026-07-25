"""搭作文·自学句适配 LLM 结果缓存(第三方付费必缓存):essay_adapt_cache。幂等。

Revision ID: m197_essay_adapt_cache
Revises: m196_media_asset_ls_progress
Create Date: 2026-07-25
"""
from alembic import op

revision = "m197_essay_adapt_cache"
down_revision = "m196_media_asset_ls_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS essay_adapt_cache (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL,
            cache_key VARCHAR(64) NOT NULL,
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_essay_adapt_cache UNIQUE (student_id, cache_key)
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS essay_adapt_cache")
