"""long_sentence_favorite:学生收藏长难句。

Revision ID: m107_ls_favorite
Revises: m106_ls_audio_url
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m107_ls_favorite"
down_revision = "m106_ls_audio_url"
branch_labels = None
depends_on = None


def _has_table(t):
    return sa.inspect(op.get_bind()).has_table(t)


def upgrade():
    if not _has_table("long_sentence_favorite"):
        op.create_table(
            "long_sentence_favorite",
            sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("long_sentence_id", UUID(as_uuid=True),
                      sa.ForeignKey("long_sentence.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ls_favorite_user", "long_sentence_favorite", ["user_id"])


def downgrade():
    if _has_table("long_sentence_favorite"):
        op.drop_index("ix_ls_favorite_user", table_name="long_sentence_favorite")
        op.drop_table("long_sentence_favorite")
