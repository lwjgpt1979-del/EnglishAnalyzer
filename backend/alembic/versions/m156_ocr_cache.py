"""ocr_cache:按图片内容 md5 缓存 OCR 结果(同图不重复识别)。幂等。

Revision ID: m156_ocr_cache
Revises: m155_vocab_media_origin
Create Date: 2026-07-14
"""
from alembic import op

revision = "m156_ocr_cache"
down_revision = "m155_vocab_media_origin"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS ocr_cache (
            image_md5 VARCHAR(32) PRIMARY KEY,
            printed_text TEXT NOT NULL DEFAULT '',
            handwritten_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS ocr_cache")
