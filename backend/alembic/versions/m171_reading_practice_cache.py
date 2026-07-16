"""reading_practice_cache:阅读理解练同类(本篇短文理解新题)缓存。幂等。

Revision ID: m171_reading_practice_cache
Revises: m170_reading_analysis_cache
Create Date: 2026-07-16
"""
from alembic import op

revision = "m171_reading_practice_cache"
down_revision = "m170_reading_analysis_cache"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE TABLE IF NOT EXISTS reading_practice_cache (cache_md5 VARCHAR(32) PRIMARY KEY, questions JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")

def downgrade():
    op.execute("DROP TABLE IF EXISTS reading_practice_cache")
