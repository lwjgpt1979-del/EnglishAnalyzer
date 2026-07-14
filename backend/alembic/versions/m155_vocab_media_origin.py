"""vocab media_origin:标记学生端即时生成的单词媒体(供后台过滤复核)。幂等。

Revision ID: m155_vocab_media_origin
Revises: m154_grammar_quiz_stat
Create Date: 2026-07-14
"""
from alembic import op

revision = "m155_vocab_media_origin"
down_revision = "m154_grammar_quiz_stat"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS media_origin VARCHAR(16)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_media_origin ON vocabulary_words (media_origin)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_vocab_media_origin")
    op.execute("ALTER TABLE vocabulary_words DROP COLUMN IF EXISTS media_origin")
