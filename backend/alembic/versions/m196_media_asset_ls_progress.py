"""补历史手动 DDL 未入迁移的两处:
- vocab_media_asset 表(词力通配图/媒体版本资产,历史仅手动 DDL 建过,无迁移)。
- student_long_sentence 三态列 did_comp/did_gram/did_word(蓝-4 长难句徽章环,仅手动 DDL)。
全新生产库 upgrade head 靠这条建齐。幂等。

Revision ID: m196_media_asset_ls_progress
Revises: m195_ls_component_error
Create Date: 2026-07-23
"""
from alembic import op

revision = "m196_media_asset_ls_progress"
down_revision = "m195_ls_component_error"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_media_asset (
            id UUID PRIMARY KEY,
            word_id UUID NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            kind VARCHAR(12) NOT NULL,
            url VARCHAR NOT NULL,
            style VARCHAR,
            prompt TEXT,
            selected BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_media_asset_word_kind "
        "ON vocab_media_asset (word_id, kind)")
    # 蓝-4 徽章环三态(认成分/认语法/重点词)
    op.execute("ALTER TABLE student_long_sentence ADD COLUMN IF NOT EXISTS did_comp BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE student_long_sentence ADD COLUMN IF NOT EXISTS did_gram BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE student_long_sentence ADD COLUMN IF NOT EXISTS did_word BOOLEAN NOT NULL DEFAULT false")


def downgrade():
    op.execute("ALTER TABLE student_long_sentence DROP COLUMN IF EXISTS did_word")
    op.execute("ALTER TABLE student_long_sentence DROP COLUMN IF EXISTS did_gram")
    op.execute("ALTER TABLE student_long_sentence DROP COLUMN IF EXISTS did_comp")
    op.execute("DROP TABLE IF EXISTS vocab_media_asset")
