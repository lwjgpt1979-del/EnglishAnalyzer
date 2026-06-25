"""R10.5 语法间隔复测:student_grammar_mastery 加保持/复测排期列。

mastered_at(四维门槛首达时间)· next_retain_at(下次复测到期)·
retain_interval_days(当前间隔)· retain_count(已通过复测次数)。

Revision ID: m116_grammar_retention
Revises: m115_grammar_probes
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "m116_grammar_retention"
down_revision = "m115_grammar_probes"
branch_labels = None
depends_on = None

_COLS = {
    "mastered_at": sa.Column("mastered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    "next_retain_at": sa.Column("next_retain_at", sa.TIMESTAMP(timezone=True), nullable=True),
    "retain_interval_days": sa.Column("retain_interval_days", sa.Integer(), nullable=False,
                                      server_default=sa.text("0")),
    "retain_count": sa.Column("retain_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
}


def _existing():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("student_grammar_mastery")}


def upgrade():
    have = _existing()
    for name, col in _COLS.items():
        if name not in have:
            op.add_column("student_grammar_mastery", col)


def downgrade():
    have = _existing()
    for name in _COLS:
        if name in have:
            op.drop_column("student_grammar_mastery", name)
