"""行政区划地区表 region(省/市/区县/乡镇,parent_code 任意层级)。带存在性保护。

Revision ID: m94_region
Revises: m93_real_extract_job
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "m94_region"
down_revision = "m93_real_extract_job"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("region"):
        op.create_table(
            "region",
            sa.Column("code", sa.String(12), primary_key=True),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("parent_code", sa.String(12), nullable=True),
            sa.Column("level", sa.SmallInteger(), nullable=False),
        )
        op.create_index("ix_region_parent", "region", ["parent_code"])
        op.create_index("ix_region_level", "region", ["level"])


def downgrade() -> None:
    if _has("region"):
        op.drop_index("ix_region_level", table_name="region")
        op.drop_index("ix_region_parent", table_name="region")
        op.drop_table("region")
