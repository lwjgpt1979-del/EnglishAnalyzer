"""grammar_quiz_stat:长难句语法提问式选择的正确率统计(以往至今累计)。幂等。

Revision ID: m154_grammar_quiz_stat
Revises: m153_vocab_review
Create Date: 2026-07-14
"""
from alembic import op

revision = "m154_grammar_quiz_stat"
down_revision = "m153_vocab_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_grammar_quiz_stat (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL,
            gp_key VARCHAR(64) NOT NULL,          -- 语法点稳定键(node_id 或 name:归一名)
            node_id UUID,                         -- 匹配到的语法节点(有则可跳讲解)
            label VARCHAR(120) NOT NULL,          -- 展示名
            correct INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_grammar_quiz_stat_student_gp UNIQUE (student_id, gp_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_grammar_quiz_stat_student ON student_grammar_quiz_stat (student_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS student_grammar_quiz_stat")
