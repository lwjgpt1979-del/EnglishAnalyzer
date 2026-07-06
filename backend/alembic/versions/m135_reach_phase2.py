"""域24 Phase2: 生命周期自动化 + SMS 渠道 + 触达明细。

reach_campaign +recurring/enabled/total_reached;新表 reach_log(触达明细,recurring 去重)。

Revision ID: m135_reach_phase2
Revises: m134_reach_crm
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "m135_reach_phase2"
down_revision = "m134_reach_crm"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reach_campaign", sa.Column(
        "recurring", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("reach_campaign", sa.Column(
        "enabled", sa.Boolean, nullable=False, server_default=sa.text("true")))
    op.add_column("reach_campaign", sa.Column(
        "total_reached", sa.Integer, nullable=False, server_default=sa.text("0")))
    op.create_table(
        "reach_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("reach_campaign.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("reached_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reach_log_campaign_user", "reach_log", ["campaign_id", "user_id"])


def downgrade():
    op.drop_index("ix_reach_log_campaign_user", table_name="reach_log")
    op.drop_table("reach_log")
    op.drop_column("reach_campaign", "total_reached")
    op.drop_column("reach_campaign", "enabled")
    op.drop_column("reach_campaign", "recurring")
