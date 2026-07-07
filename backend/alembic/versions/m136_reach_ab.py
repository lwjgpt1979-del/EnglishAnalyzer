"""域24 Phase3: A/B 文案 —— reach_campaign.variants + reach_log.variant。

Revision ID: m136_reach_ab
Revises: m135_reach_phase2
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m136_reach_ab"
down_revision = "m135_reach_phase2"
branch_labels = None
depends_on = None


def upgrade():
    # 多文案变体:[{"label":"A","title":..,"content":..}, ...];空/NULL=单文案(用 title/content)
    op.add_column("reach_campaign", sa.Column("variants", JSONB, nullable=True))
    # 该次触达命中的变体标签(A/B 归因)
    op.add_column("reach_log", sa.Column("variant", sa.String(8), nullable=True))


def downgrade():
    op.drop_column("reach_log", "variant")
    op.drop_column("reach_campaign", "variants")
