"""vocabulary_words.media_report_count:学生「图不对」反馈计数(P3)。幂等。

Revision ID: m174_vocab_media_report_count
Revises: m173_vocab_image_verify_cache
Create Date: 2026-07-17
"""
from alembic import op

revision = "m174_vocab_media_report_count"
down_revision = "m173_vocab_image_verify_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE vocabulary_words "
        "ADD COLUMN IF NOT EXISTS media_report_count INTEGER NOT NULL DEFAULT 0"
    )


def downgrade():
    op.execute("ALTER TABLE vocabulary_words DROP COLUMN IF EXISTS media_report_count")
