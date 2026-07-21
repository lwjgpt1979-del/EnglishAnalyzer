"""考点报错闭环(P6):vocab_word_relation.report_count(学生报错数)。幂等。

Revision ID: m193_vocab_relation_report
Revises: m192_vocab_word_kp_review
Create Date: 2026-07-20
"""
from alembic import op

revision = "m193_vocab_relation_report"
down_revision = "m192_vocab_word_kp_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_word_relation ADD COLUMN IF NOT EXISTS report_count INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE vocab_word_relation DROP COLUMN IF EXISTS report_count")
