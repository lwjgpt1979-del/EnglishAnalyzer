"""生成内容暂存 pending_kp_content(KP 未命中 node 时存,候选审核后物化)。带存在性保护。

Revision ID: m91_pending_kp_content
Revises: m90_long_sentence
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m91_pending_kp_content"
down_revision = "m90_long_sentence"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("pending_kp_content"):
        op.create_table(
            "pending_kp_content",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("kp_name_norm", sa.String(), nullable=False),
            sa.Column("dimension", sa.String(16), nullable=False),
            sa.Column("content_md", sa.Text(), nullable=False),
            sa.Column("source_unit_id", UUID(as_uuid=True), nullable=True),
            sa.Column("generated_by", sa.String(24), nullable=False, server_default="ai_full"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("kp_name_norm", "dimension", name="uix_pending_kp_dim"),
        )
        op.create_index("ix_pending_kp_content_norm", "pending_kp_content", ["kp_name_norm"])


def downgrade() -> None:
    if _has("pending_kp_content"):
        op.drop_index("ix_pending_kp_content_norm", table_name="pending_kp_content")
        op.drop_table("pending_kp_content")
