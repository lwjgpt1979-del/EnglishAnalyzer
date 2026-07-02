"""sales_lead 增加 tags(运营标签,与 biz_tags 经营特征区分)。幂等。

Revision ID: m126_sales_lead_tags
Revises: m125_wecom_archive
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m126_sales_lead_tags"
down_revision = "m125_wecom_archive"
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "tags" not in _cols("sales_lead"):
        op.add_column("sales_lead", sa.Column("tags", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("sales_lead", "tags")
