"""student_wrong_relation:错题关系网(每个学生私有,节点=错题选项词/词组,边=同题选项关系)。幂等。

Revision ID: m183_student_wrong_relation
Revises: m182_vocab_kp_mcq
Create Date: 2026-07-19
"""
from alembic import op

revision = "m183_student_wrong_relation"
down_revision = "m182_vocab_kp_mcq"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_wrong_relation (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            a_word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            b_word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            relation VARCHAR(16) NOT NULL,
            source VARCHAR(8) NOT NULL,
            wrong_record_id UUID REFERENCES wrong_record(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_student_wrong_relation UNIQUE (student_id, a_word_id, b_word_id, relation)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_wrong_relation_student "
               "ON student_wrong_relation(student_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS student_wrong_relation")
