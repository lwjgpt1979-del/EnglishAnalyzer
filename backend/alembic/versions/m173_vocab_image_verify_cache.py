"""vocab_image_verify_cache:配图图文一致复核(P2·⑥C)结果缓存,按图 md5。幂等。

Revision ID: m173_vocab_image_verify_cache
Revises: m172_reading_question_studied
Create Date: 2026-07-16
"""
from alembic import op

revision = "m173_vocab_image_verify_cache"
down_revision = "m172_reading_question_studied"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE IF NOT EXISTS vocab_image_verify_cache ("
        "img_md5 VARCHAR(32) PRIMARY KEY, "
        "result JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_image_verify_cache")
