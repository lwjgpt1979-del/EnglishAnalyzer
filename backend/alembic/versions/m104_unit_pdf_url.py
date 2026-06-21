"""curriculum_units 加 unit_pdf_url:拆出的单元独立 PDF(COS 直链)。

Revision ID: m104_unit_pdf
Revises: m103_unit_src
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op

revision = "m104_unit_pdf"
down_revision = "m103_unit_src"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("curriculum_units", sa.Column("unit_pdf_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("curriculum_units", "unit_pdf_url")
