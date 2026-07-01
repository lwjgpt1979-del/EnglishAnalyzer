"""platform_paper 增加 source_file_url(批量上传真题:原卷 word/pdf 存 COS 的直链)。

批量上传 = 每份文件传 COS + 建草稿试卷占位(0 题),题目延后解析。幂等:列已存在则跳过。

Revision ID: m121_paper_source_file
Revises: m120_unit_structured
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "m121_paper_source_file"
down_revision = "m120_unit_structured"
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _cols("platform_paper")
    if "source_file_url" not in cols:
        op.add_column("platform_paper", sa.Column("source_file_url", sa.String(512), nullable=True))
    if "source_filename" not in cols:
        op.add_column("platform_paper", sa.Column("source_filename", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_paper", "source_filename")
    op.drop_column("platform_paper", "source_file_url")
