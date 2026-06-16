"""敏感词库（§5.6）：sensitive_words

超管动态维护敏感词，用于内容过滤。带存在性保护，可重复 upgrade head。

Revision ID: m73_sensitive_words
Revises: m72_ocr_corrected
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m73_sensitive_words"
down_revision = "m72_ocr_corrected"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "sensitive_words" not in _insp().get_table_names():
        op.create_table(
            "sensitive_words",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("word", sa.String(64), nullable=False, unique=True),
            sa.Column("category", sa.String(20), nullable=False, server_default="other"),
            sa.Column("action", sa.String(10), nullable=False, server_default="block"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_sensitive_words_active", "sensitive_words", ["is_active"])


def downgrade() -> None:
    if "sensitive_words" in _insp().get_table_names():
        op.drop_table("sensitive_words")
