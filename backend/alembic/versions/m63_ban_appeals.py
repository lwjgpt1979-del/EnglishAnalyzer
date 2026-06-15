"""封禁申诉（§5.3.1）：ban_appeals 表

被封用户提交申诉 → 后台审核；通过则解封（解封自动顺延会员=补偿封禁时长）。
带存在性保护，可重复 upgrade head。

Revision ID: m63_ban_appeals
Revises: m62_listening_weak
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m63_ban_appeals"
down_revision = "m62_listening_weak"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "ban_appeals" not in _insp().get_table_names():
        op.create_table(
            "ban_appeals",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("evidence_urls", JSONB(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index("ix_ban_appeals_user", "ban_appeals", ["user_id", "created_at"])
        op.create_index("ix_ban_appeals_status", "ban_appeals", ["status", "created_at"])


def downgrade() -> None:
    if "ban_appeals" in _insp().get_table_names():
        op.drop_table("ban_appeals")
