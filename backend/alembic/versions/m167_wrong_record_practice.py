"""wrong_record 加练同类作答统计(方案B:待巩固/巩固中区分 + 掌握判定)。幂等。

Revision ID: m167_wrong_record_practice
Revises: m166_drop_legacy_wrong_questions
Create Date: 2026-07-15
"""
from alembic import op

revision = "m167_wrong_record_practice"
down_revision = "m166_drop_legacy_wrong_questions"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS practice_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS practice_correct INTEGER NOT NULL DEFAULT 0")

def downgrade():
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS practice_count")
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS practice_correct")
