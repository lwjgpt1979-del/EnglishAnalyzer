"""platform_paper 增加 year(从试卷名自动提取的年份,便于按年份筛选/排序)。幂等。

Revision ID: m123_paper_year
Revises: m122_paper_parse_status
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "m123_paper_year"
down_revision = "m122_paper_parse_status"
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "year" not in _cols("platform_paper"):
        op.add_column("platform_paper", sa.Column("year", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_paper", "year")
