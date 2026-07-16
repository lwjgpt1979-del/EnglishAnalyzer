"""user_paper_sections.in_reading_intensive:阅读理解手动加入作业精讲开关(默认否)。幂等。

Revision ID: m169_section_reading_intensive
Revises: m168_wrong_record_vocab_word
Create Date: 2026-07-16
"""
from alembic import op

revision = "m169_section_reading_intensive"
down_revision = "m168_wrong_record_vocab_word"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE user_paper_sections ADD COLUMN IF NOT EXISTS in_reading_intensive BOOLEAN NOT NULL DEFAULT false")

def downgrade():
    op.execute("ALTER TABLE user_paper_sections DROP COLUMN IF EXISTS in_reading_intensive")
