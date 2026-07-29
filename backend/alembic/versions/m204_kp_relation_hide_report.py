"""考点关系:下架态 + 有凭证举报表(方案1·自动上架+举报下架)。

Revision ID: m204_kp_relation_hide_report
Revises: m203_dict_ecdict_exchange
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op

revision = "m204_kp_relation_hide_report"
down_revision = "m203_dict_ecdict_exchange"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE vocab_word_relation
          ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS hidden_by UUID,
          ADD COLUMN IF NOT EXISTS hide_note TEXT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_kp_relation_report (
            id UUID PRIMARY KEY,
            relation_id UUID NOT NULL REFERENCES vocab_word_relation(id) ON DELETE CASCADE,
            student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reason VARCHAR(32) NOT NULL,
            detail TEXT,
            suggested TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (relation_id, student_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_kp_rel_report_rel ON vocab_kp_relation_report (relation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_kp_rel_report_created ON vocab_kp_relation_report (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_word_relation_hidden ON vocab_word_relation (hidden_at) WHERE hidden_at IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vocab_word_relation_hidden")
    op.execute("DROP INDEX IF EXISTS ix_vocab_kp_rel_report_created")
    op.execute("DROP INDEX IF EXISTS ix_vocab_kp_rel_report_rel")
    op.execute("DROP TABLE IF EXISTS vocab_kp_relation_report")
    op.execute("""
        ALTER TABLE vocab_word_relation
          DROP COLUMN IF EXISTS hide_note,
          DROP COLUMN IF EXISTS hidden_by,
          DROP COLUMN IF EXISTS hidden_at
    """)
