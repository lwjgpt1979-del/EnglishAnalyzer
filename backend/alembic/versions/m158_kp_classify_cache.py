"""kp_classify_cache:题目归类结果按小题内容 md5 缓存(重叠题不重复归类)。幂等。

Revision ID: m158_kp_classify_cache
Revises: m157_paper_content_dedup
Create Date: 2026-07-14
"""
from alembic import op

revision = "m158_kp_classify_cache"
down_revision = "m157_paper_content_dedup"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS kp_classify_cache (
            content_md5 VARCHAR(32) PRIMARY KEY,
            kp_key VARCHAR(120) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS kp_classify_cache")
