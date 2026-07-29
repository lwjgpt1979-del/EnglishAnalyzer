"""vocab_word_kp.prehide_at:二期 AI 预隐已跑标记(低峰扫中考高频近义/易混)。

Revision ID: m205_kp_prehide_at
Revises: m204_kp_relation_hide_report
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op

revision = "m205_kp_prehide_at"
down_revision = "m204_kp_relation_hide_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE vocab_word_kp ADD COLUMN IF NOT EXISTS prehide_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_word_kp_prehide "
        "ON vocab_word_kp (prehide_at) WHERE prehide_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vocab_word_kp_prehide")
    op.execute("ALTER TABLE vocab_word_kp DROP COLUMN IF EXISTS prehide_at")
