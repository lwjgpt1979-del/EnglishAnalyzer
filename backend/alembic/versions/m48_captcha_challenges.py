"""create captcha_challenges table (M48 图形验证码防盗刷)

Revision ID: m48_captcha
Revises: m47_sms_verify
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "m48_captcha"
down_revision = "m47_sms_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "captcha_challenges",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("answer", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("captcha_challenges")
