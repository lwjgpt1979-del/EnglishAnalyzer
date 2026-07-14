"""user_uploaded_papers 加 image_md5s(每张图 md5,子集去重)。幂等。

Revision ID: m160_paper_image_md5s
Revises: m159_paper_split_cache
Create Date: 2026-07-14
"""
from alembic import op

revision = "m160_paper_image_md5s"
down_revision = "m159_paper_split_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_uploaded_papers ADD COLUMN IF NOT EXISTS image_md5s JSONB")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_papers_image_md5s ON user_uploaded_papers USING gin (image_md5s)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_papers_image_md5s")
    op.execute("ALTER TABLE user_uploaded_papers DROP COLUMN IF EXISTS image_md5s")
