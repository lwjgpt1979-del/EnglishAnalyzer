"""reading_analysis_cache:阅读精讲题目层解析缓存(第三方付费暂存)。幂等。

Revision ID: m170_reading_analysis_cache
Revises: m169_section_reading_intensive
Create Date: 2026-07-16
"""
from alembic import op

revision = "m170_reading_analysis_cache"
down_revision = "m169_section_reading_intensive"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE TABLE IF NOT EXISTS reading_analysis_cache (q_md5 VARCHAR(32) PRIMARY KEY, analysis JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")

def downgrade():
    op.execute("DROP TABLE IF EXISTS reading_analysis_cache")
