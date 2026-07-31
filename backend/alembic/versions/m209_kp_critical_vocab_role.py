"""m209 stub: KP 重点词相关列(历史已落地 DB;文件曾删,补回以接 alembic 链)。

Revision ID: m209_kp_critical_vocab_role
Revises: m208_kp_title_rewrite_cache
"""
from __future__ import annotations

from alembic import op

revision = "m209_kp_critical_vocab_role"
down_revision = "m218_unit_understand_ls_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等:本地库已执行过本 revision
    op.execute(
        "ALTER TABLE vocab_node ADD COLUMN IF NOT EXISTS role VARCHAR(16) "
        "NOT NULL DEFAULT 'derived'"
    )
    op.execute(
        "ALTER TABLE vocab_node ADD COLUMN IF NOT EXISTS sort_order SMALLINT "
        "NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE vocab_node ADD COLUMN IF NOT EXISTS note TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_node_node_role "
        "ON vocab_node (node_id, role)"
    )
    op.execute(
        "ALTER TABLE vocab_question ADD COLUMN IF NOT EXISTS link_kind VARCHAR(16) "
        "NOT NULL DEFAULT 'occur'"
    )


def downgrade() -> None:
    pass
