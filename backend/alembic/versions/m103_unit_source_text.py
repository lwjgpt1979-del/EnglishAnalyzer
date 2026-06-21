"""curriculum_units 加 source_text:存 PDF 生成时的单元原文,供重生成/析短文。

Revision ID: m103_unit_src
Revises: m102_passage_kp
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op

revision = "m103_unit_src"
down_revision = "m102_passage_kp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("curriculum_units", sa.Column("source_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("curriculum_units", "source_text")
