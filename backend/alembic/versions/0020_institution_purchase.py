"""机构学生采购：institution_purchases + activation_codes（D-122）

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

# 复用已存在的 membership_tier 枚举，不重复建类型
_tier = postgresql.ENUM(
    "free", "basic", "pro", "promax", name="membership_tier", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "institution_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("tier", _tier, nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'paid'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_institution_purchases_institution_id",
                    "institution_purchases", ["institution_id"])
    op.create_table(
        "activation_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=12), nullable=False, unique=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("institution_purchases.id"), nullable=False),
        sa.Column("tier", _tier, nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'unused'")),
        sa.Column("used_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_activation_codes_purchase_id", "activation_codes", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_activation_codes_purchase_id", table_name="activation_codes")
    op.drop_table("activation_codes")
    op.drop_index("ix_institution_purchases_institution_id", table_name="institution_purchases")
    op.drop_table("institution_purchases")
