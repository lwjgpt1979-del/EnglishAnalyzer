"""vocab_kp_mcq.report_count:学生「换一题」报错标记(后台复核 AI 出错题)。幂等。

Revision ID: m188_vocab_kp_mcq_report
Revises: m187_vocab_word_sense
Create Date: 2026-07-20
"""
from alembic import op

revision = "m188_vocab_kp_mcq_report"
down_revision = "m187_vocab_word_sense"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_kp_mcq ADD COLUMN IF NOT EXISTS report_count INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE vocab_kp_mcq DROP COLUMN IF EXISTS report_count")
