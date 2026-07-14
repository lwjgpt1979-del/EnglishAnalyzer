"""student_grammar_node 加 source_paper_id(个人语法按卷归组进作业精讲·语法)。幂等。

Revision ID: m161_sgn_source_paper
Revises: m160_paper_image_md5s
Create Date: 2026-07-14
"""
from alembic import op

revision = "m161_sgn_source_paper"
down_revision = "m160_paper_image_md5s"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE student_grammar_node ADD COLUMN IF NOT EXISTS source_paper_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sgn_paper ON student_grammar_node (source_paper_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_sgn_paper")
    op.execute("ALTER TABLE student_grammar_node DROP COLUMN IF EXISTS source_paper_id")
