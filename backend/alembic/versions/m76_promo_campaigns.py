"""限时活动价（§5.7）：promo_campaigns + orders.promo_campaign_id

活动期内覆盖学期会员定价。带存在性保护，可重复 upgrade head。

Revision ID: m76_promo_campaigns
Revises: m75_price_change_log
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m76_promo_campaigns"
down_revision = "m75_price_change_log"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    names = _insp().get_table_names()
    if "promo_campaigns" not in names:
        op.create_table(
            "promo_campaigns",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("price_basic", sa.Integer(), nullable=True),
            sa.Column("price_pro", sa.Integer(), nullable=True),
            sa.Column("price_promax", sa.Integer(), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("limit_type", sa.String(10), nullable=False, server_default="none"),
            sa.Column("total_quota", sa.Integer(), nullable=True),
            sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_promotional", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_promo_campaigns_window", "promo_campaigns", ["is_active", "starts_at", "ends_at"])
    if "orders" in names and not _has_col("orders", "promo_campaign_id"):
        op.add_column("orders", sa.Column("promo_campaign_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    names = _insp().get_table_names()
    if "orders" in names and _has_col("orders", "promo_campaign_id"):
        op.drop_column("orders", "promo_campaign_id")
    if "promo_campaigns" in names:
        op.drop_table("promo_campaigns")
