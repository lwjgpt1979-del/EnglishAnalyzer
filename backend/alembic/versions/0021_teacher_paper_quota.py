"""teachers.monthly_paper_quota：机构出卷月额度（D-128）

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("monthly_paper_quota", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("teachers", "monthly_paper_quota")
