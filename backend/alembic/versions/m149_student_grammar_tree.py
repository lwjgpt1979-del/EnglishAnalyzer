"""个人语法树:student_grammar_node(未匹配图谱的个人节点)+ users.preferred_unit_no(单元进度)。幂等。

Revision ID: m149_student_grammar_tree
Revises: m148_student_kp_target
Create Date: 2026-07-11
"""
from alembic import op

revision = "m149_student_grammar_tree"
down_revision = "m148_student_kp_target"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_grammar_node (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL REFERENCES users(id),
            name VARCHAR(120) NOT NULL,
            name_norm VARCHAR(120) NOT NULL,
            ref_node_id UUID REFERENCES knowledge_nodes(id),
            anchor_code VARCHAR(32),
            source VARCHAR(24) NOT NULL DEFAULT 'upload_paper',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_student_grammar_node UNIQUE (student_id, name_norm)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_grammar_node_student ON student_grammar_node (student_id)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_unit_no INTEGER")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_unit_no")
    op.execute("DROP TABLE IF EXISTS student_grammar_node")
