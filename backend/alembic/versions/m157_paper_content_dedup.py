"""user_uploaded_papers 加 content_hash + duplicate_of(同卷重拍去重)。幂等。

Revision ID: m157_paper_content_dedup
Revises: m156_ocr_cache
Create Date: 2026-07-14
"""
from alembic import op

revision = "m157_paper_content_dedup"
down_revision = "m156_ocr_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_uploaded_papers ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32)")
    op.execute("ALTER TABLE user_uploaded_papers ADD COLUMN IF NOT EXISTS duplicate_of UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_papers_content_hash ON user_uploaded_papers (content_hash)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_papers_content_hash")
    op.execute("ALTER TABLE user_uploaded_papers DROP COLUMN IF EXISTS duplicate_of")
    op.execute("ALTER TABLE user_uploaded_papers DROP COLUMN IF EXISTS content_hash")
