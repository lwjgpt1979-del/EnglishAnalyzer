"""渠道来源（§5.5）：users.acquisition_channel

注册时一次性写入获客渠道，用于数据大盘渠道分布分析。带存在性保护，可重复 upgrade head。

Revision ID: m70_acquisition_channel
Revises: m69_coupons
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m70_acquisition_channel"
down_revision = "m69_coupons"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    if "users" in _insp().get_table_names() and not _has_col("users", "acquisition_channel"):
        op.add_column("users", sa.Column("acquisition_channel", sa.String(20), nullable=True))


def downgrade() -> None:
    if "users" in _insp().get_table_names() and _has_col("users", "acquisition_channel"):
        op.drop_column("users", "acquisition_channel")
