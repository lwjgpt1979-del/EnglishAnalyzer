"""add source column to institutions (M49 区分自助申请/手动录入)

Revision ID: m49_inst_source
Revises: m48_captcha
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "m49_inst_source"
down_revision = "m48_captcha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史数据均为超管手动录入，默认 'admin'
    op.add_column(
        "institutions",
        sa.Column("source", sa.String(length=20), nullable=False,
                  server_default=sa.text("'admin'")),
    )


def downgrade() -> None:
    op.drop_column("institutions", "source")
