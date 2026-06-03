"""vocab media fields: image_urls/en_description/audio/media_status (词力通图背单词)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocabulary_words", sa.Column("image_urls", postgresql.JSONB(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("en_description", sa.Text(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("word_audio_url", sa.String(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("en_desc_audio_url", sa.String(), nullable=True))
    op.add_column("vocabulary_words", sa.Column(
        "media_status", sa.String(), nullable=False, server_default=sa.text("'draft'")
    ))


def downgrade() -> None:
    op.drop_column("vocabulary_words", "media_status")
    op.drop_column("vocabulary_words", "en_desc_audio_url")
    op.drop_column("vocabulary_words", "word_audio_url")
    op.drop_column("vocabulary_words", "en_description")
    op.drop_column("vocabulary_words", "image_urls")
