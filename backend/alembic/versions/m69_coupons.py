"""优惠券 / 兑换码（SP-4）：coupons · coupon_grants + orders 抵扣列

后台发券（直发/兑换码批量）→ 用户领取 → 下单抵扣。带存在性保护，可重复 upgrade head。

Revision ID: m69_coupons
Revises: m68_user_feedback
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m69_coupons"
down_revision = "m68_user_feedback"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    names = _insp().get_table_names()
    if "coupons" not in names:
        op.create_table(
            "coupons",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("discount_type", sa.String(10), nullable=False),   # amount|percent
            sa.Column("discount_value", sa.Integer(), nullable=False),   # 分 | 万分比
            sa.Column("min_amount_fen", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_discount_fen", sa.Integer(), nullable=True),
            sa.Column("scope", sa.String(20), nullable=False, server_default="all"),
            sa.Column("redeem_code", sa.String(20), nullable=True, unique=True),
            sa.Column("redeem_quota", sa.Integer(), nullable=True),
            sa.Column("redeemed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if "coupon_grants" not in names:
        op.create_table(
            "coupon_grants",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("coupon_id", UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(10), nullable=False, server_default="unused"),
            sa.Column("order_id", UUID(as_uuid=True), nullable=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_coupon_grants_user", "coupon_grants", ["user_id", "status"])
    # orders 抵扣列
    if "orders" in names:
        if not _has_col("orders", "coupon_grant_id"):
            op.add_column("orders", sa.Column("coupon_grant_id", UUID(as_uuid=True), nullable=True))
        if not _has_col("orders", "discount_fen"):
            op.add_column("orders", sa.Column("discount_fen", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    names = _insp().get_table_names()
    if "orders" in names:
        if _has_col("orders", "discount_fen"):
            op.drop_column("orders", "discount_fen")
        if _has_col("orders", "coupon_grant_id"):
            op.drop_column("orders", "coupon_grant_id")
    if "coupon_grants" in names:
        op.drop_table("coupon_grants")
    if "coupons" in names:
        op.drop_table("coupons")
