"""地区↔英语教材版本对应表 region_textbook(省级默认+可校对+地市例外)。

Revision ID: m130_region_textbook
Revises: m129_map_crawl_progress
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m130_region_textbook"
down_revision = "m129_map_crawl_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "region_textbook",
        sa.Column("region_code", sa.String(12), primary_key=True),
        sa.Column("region_name", sa.String(64), nullable=False),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("versions", JSONB, nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_region_textbook_level", "region_textbook", ["level"])


def downgrade():
    op.drop_index("ix_region_textbook_level", table_name="region_textbook")
    op.drop_table("region_textbook")
