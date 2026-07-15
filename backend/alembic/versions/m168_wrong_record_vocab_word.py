"""wrong_record.vocab_word_id(词汇错题定位到的目标词,词力通双维闭环 P3)。幂等。

Revision ID: m168_wrong_record_vocab_word
Revises: m167_wrong_record_practice
Create Date: 2026-07-15
"""
from alembic import op

revision = "m168_wrong_record_vocab_word"
down_revision = "m167_wrong_record_practice"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS vocab_word_id UUID")

def downgrade():
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS vocab_word_id")
