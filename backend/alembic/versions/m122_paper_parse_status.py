"""platform_paper 增加 parse_status(批量上传后「解析原题目」的状态标注)。

值:空/None=未解析(占位) | parsing=解析中 | parsed=已解析 | failed=失败。幂等。

Revision ID: m122_paper_parse_status
Revises: m121_paper_source_file
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "m122_paper_parse_status"
down_revision = "m121_paper_source_file"
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "parse_status" not in _cols("platform_paper"):
        op.add_column("platform_paper", sa.Column("parse_status", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_paper", "parse_status")
