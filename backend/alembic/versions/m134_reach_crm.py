"""域24: 存量召回/分群触达 —— user_segment + reach_campaign。

⚠️ 并行注:本迁移链在 m132(main 头)。dev 库另有并行会话的 m133_task_run(任务看板)。
待 m133_task_run 落 main 后,main 会有 m132 的两个子头(m133/m134),需 `alembic merge heads`
生成一条合并迁移即可(5 分钟)。

Revision ID: m134_reach_crm
Revises: m132_users_admin_modules
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m134_reach_crm"
down_revision = "m132_users_admin_modules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_segment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("rule", JSONB, nullable=False, server_default=sa.text("'{\"conditions\": []}'")),
        sa.Column("last_count", sa.Integer, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "reach_campaign",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("segment_id", UUID(as_uuid=True),
                  sa.ForeignKey("user_segment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_snapshot", JSONB, nullable=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("lead_tag", sa.String(40), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("stats", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_reach_campaign_created", "reach_campaign", ["created_at"])


def downgrade():
    op.drop_index("ix_reach_campaign_created", table_name="reach_campaign")
    op.drop_table("reach_campaign")
    op.drop_table("user_segment")
