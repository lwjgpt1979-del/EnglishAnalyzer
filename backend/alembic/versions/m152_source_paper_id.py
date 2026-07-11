"""待学习三表加 source_paper_id(作业精讲按批次归组)。幂等。

Revision ID: m152_source_paper_id
Revises: m151_sentence_analysis_cache
Create Date: 2026-07-11
"""
from alembic import op

revision = "m152_source_paper_id"
down_revision = "m151_sentence_analysis_cache"
branch_labels = None
depends_on = None

_TABLES = ["student_kp_target", "student_vocab_candidates", "student_long_sentence"]


def upgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS source_paper_id UUID")


def downgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS source_paper_id")
