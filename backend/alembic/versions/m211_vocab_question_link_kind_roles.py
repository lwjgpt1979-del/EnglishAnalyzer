"""m211: vocab_question.link_kind 允许 correct/distractor(选项挂词)。

历史 ck 仅 occur|focus,挂主考/干扰会 CheckViolation → 批量采纳 1 成 N 败。

Revision ID: m211_vocab_question_link_kind_roles
Revises: m210_vocab_question_option_role
"""
from __future__ import annotations

from alembic import op

revision = "m211_vocab_question_link_kind_roles"
down_revision = "m210_vocab_question_option_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE vocab_question DROP CONSTRAINT IF EXISTS ck_vocab_question_link_kind")
    op.execute(
        "ALTER TABLE vocab_question ADD CONSTRAINT ck_vocab_question_link_kind "
        "CHECK (link_kind IN ('occur', 'focus', 'correct', 'distractor'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE vocab_question DROP CONSTRAINT IF EXISTS ck_vocab_question_link_kind")
    op.execute(
        "ALTER TABLE vocab_question ADD CONSTRAINT ck_vocab_question_link_kind "
        "CHECK (link_kind IN ('occur', 'focus'))"
    )
