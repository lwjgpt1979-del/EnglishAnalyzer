"""错题本重构(P1):wrong_record 加 dim(练习衍生考点维)+ practice_streak(连对计数)。幂等。

Revision ID: m194_wrong_record_practice
Revises: m193_vocab_relation_report
Create Date: 2026-07-21
"""
from alembic import op

revision = "m194_wrong_record_practice"
down_revision = "m193_vocab_relation_report"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS dim VARCHAR(16)")
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS practice_streak SMALLINT NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS practice_streak")
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS dim")
