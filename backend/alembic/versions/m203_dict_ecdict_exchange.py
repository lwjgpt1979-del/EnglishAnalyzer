"""dict_ecdict 加 exchange(ECDICT 词形交换码):供形态学打底补不规则变化。

Revision ID: m203_dict_ecdict_exchange
Revises: m202_grammar_source_question
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op

revision = "m203_dict_ecdict_exchange"
down_revision = "m202_grammar_source_question"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE dict_ecdict ADD COLUMN IF NOT EXISTS exchange VARCHAR(256)")


def downgrade() -> None:
    op.execute("ALTER TABLE dict_ecdict DROP COLUMN IF EXISTS exchange")
