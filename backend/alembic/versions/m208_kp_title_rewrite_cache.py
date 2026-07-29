"""m208: 语法点标题 AI 整理全局缓存(按 name+description 输入 md5)。

Revision ID: m208_kp_title_rewrite_cache
Revises: m207_cloze_intensive
Create Date: 2026-07-29
"""
from __future__ import annotations

from alembic import op

revision = "m208_kp_title_rewrite_cache"
down_revision = "m207_cloze_intensive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS kp_title_rewrite_cache ("
        "input_md5 VARCHAR(32) PRIMARY KEY, "
        "title VARCHAR(120) NOT NULL, "
        "detail TEXT, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kp_title_rewrite_cache")
