"""create sms_verifications table (M47 机构自助入驻验证码)

通用短信验证码表：服务于没有账号的申请人（如机构入驻申请）按手机号+用途验证。

Revision ID: m47_sms_verify
Revises: m46_snapshots
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "m47_sms_verify"
down_revision = "m46_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_verifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sms_verifications_phone_purpose",
        "sms_verifications", ["phone", "purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_sms_verifications_phone_purpose", table_name="sms_verifications")
    op.drop_table("sms_verifications")
