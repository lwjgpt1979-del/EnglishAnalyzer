"""m218: 理解向长难句增加难度档 tier + 语法点 grammar_point.

Revision ID: m218_unit_understand_ls_tier
Revises: m217_unit_ls_understand
"""
from __future__ import annotations

from alembic import op


revision = "m218_unit_understand_ls_tier"
down_revision = "m217_unit_ls_understand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE unit_understand_ls "
        "ADD COLUMN IF NOT EXISTS tier INTEGER"
    )
    op.execute(
        "ALTER TABLE unit_understand_ls "
        "ADD COLUMN IF NOT EXISTS grammar_point VARCHAR(120)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE unit_understand_ls DROP COLUMN IF EXISTS grammar_point")
    op.execute("ALTER TABLE unit_understand_ls DROP COLUMN IF EXISTS tier")
