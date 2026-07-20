"""student_wrong_word:以词为中心的错题关系网(词在错题里的角色 主/次)。幂等。

Revision ID: m185_student_wrong_word
Revises: m184_vocab_rel_dyn_dims
Create Date: 2026-07-20
"""
from alembic import op

revision = "m185_student_wrong_word"
down_revision = "m184_vocab_rel_dyn_dims"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_wrong_word (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            wrong_record_id UUID NOT NULL REFERENCES wrong_record(id) ON DELETE CASCADE,
            role VARCHAR(10) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_student_wrong_word UNIQUE (student_id, word_id, wrong_record_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_wrong_word_sw ON student_wrong_word(student_id, word_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_wrong_word_rec ON student_wrong_word(wrong_record_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS student_wrong_word")
