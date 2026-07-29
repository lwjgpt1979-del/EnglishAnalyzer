"""paper_q_explain_cache:作业小题「查看即生成」解析全局缓存(按题面 md5)。

Revision ID: m206_paper_q_explain_cache
Revises: m205_kp_prehide_at
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op

revision = "m206_paper_q_explain_cache"
down_revision = "m205_kp_prehide_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS paper_q_explain_cache ("
        "content_md5 VARCHAR(32) PRIMARY KEY, "
        "explanation TEXT NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS paper_q_explain_cache")
