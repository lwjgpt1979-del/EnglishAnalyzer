"""m210: vocab_question 选项挂词 — option_key + link_kind∈{occur,correct,distractor}。

Revision ID: m210_vocab_question_option_role
Revises: m209_kp_critical_vocab_role
"""
from __future__ import annotations

from alembic import op

revision = "m210_vocab_question_option_role"
down_revision = "m209_kp_critical_vocab_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE vocab_question ADD COLUMN IF NOT EXISTS option_key VARCHAR(8)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_question_word_kind "
        "ON vocab_question (word_id, q_scope, link_kind)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_question_q_kind "
        "ON vocab_question (q_scope, question_id, link_kind)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vocab_question_q_kind")
    op.execute("DROP INDEX IF EXISTS ix_vocab_question_word_kind")
    op.execute("ALTER TABLE vocab_question DROP COLUMN IF EXISTS option_key")
