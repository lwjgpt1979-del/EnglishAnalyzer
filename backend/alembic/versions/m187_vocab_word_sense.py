"""vocab_word_sense 义项层(1B 词义消歧)+ relation/mcq/wrong_word 加 sense_id。幂等。

Revision ID: m187_vocab_word_sense
Revises: m186_vocab_kp_mcq_dim32
Create Date: 2026-07-20
"""
from alembic import op

revision = "m187_vocab_word_sense"
down_revision = "m186_vocab_kp_mcq_dim32"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_word_sense (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            gloss_zh VARCHAR(120) NOT NULL,
            pos VARCHAR(16),
            sort SMALLINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_word_sense_word ON vocab_word_sense(word_id)")
    op.execute("ALTER TABLE vocab_word_relation ADD COLUMN IF NOT EXISTS sense_id UUID "
               "REFERENCES vocab_word_sense(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE vocab_kp_mcq ADD COLUMN IF NOT EXISTS sense_id UUID "
               "REFERENCES vocab_word_sense(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE student_wrong_word ADD COLUMN IF NOT EXISTS sense_id UUID "
               "REFERENCES vocab_word_sense(id) ON DELETE SET NULL")


def downgrade():
    op.execute("ALTER TABLE student_wrong_word DROP COLUMN IF EXISTS sense_id")
    op.execute("ALTER TABLE vocab_kp_mcq DROP COLUMN IF EXISTS sense_id")
    op.execute("ALTER TABLE vocab_word_relation DROP COLUMN IF EXISTS sense_id")
    op.execute("DROP TABLE IF EXISTS vocab_word_sense")
