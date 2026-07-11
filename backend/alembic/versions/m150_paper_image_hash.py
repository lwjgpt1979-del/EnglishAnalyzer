"""user_uploaded_papers.image_hash:同图重复上传去重(问题1)。幂等。

Revision ID: m150_paper_image_hash
Revises: m149_student_grammar_tree
Create Date: 2026-07-11
"""
from alembic import op

revision = "m150_paper_image_hash"
down_revision = "m149_student_grammar_tree"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_uploaded_papers ADD COLUMN IF NOT EXISTS image_hash VARCHAR(32)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_uploaded_papers_image_hash ON user_uploaded_papers (image_hash)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_uploaded_papers_image_hash")
    op.execute("ALTER TABLE user_uploaded_papers DROP COLUMN IF EXISTS image_hash")
