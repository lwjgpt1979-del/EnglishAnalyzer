"""行为埋点（§5.5 DAU/MAU）：user_activity 表（每用户每天一条活跃记录）

中间件按 token 去重写入；大盘据此算 DAU/MAU/活跃趋势。
带存在性保护，可重复 upgrade head。

Revision ID: m64_user_activity
Revises: m63_ban_appeals
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m64_user_activity"
down_revision = "m63_ban_appeals"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if "user_activity" not in _insp().get_table_names():
        op.create_table(
            "user_activity",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("active_date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("uix_user_activity", "user_activity", ["user_id", "active_date"], unique=True)
        op.create_index("ix_user_activity_date", "user_activity", ["active_date"])


def downgrade() -> None:
    if "user_activity" in _insp().get_table_names():
        op.drop_table("user_activity")
