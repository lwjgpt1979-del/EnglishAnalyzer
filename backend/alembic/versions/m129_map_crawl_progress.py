"""地图获客「按区县自动采集」覆盖进度表 map_crawl_progress。

每日任务据此挑未采区县续采;粒度=区县(map API region 只可靠到区县)。

Revision ID: m129_map_crawl_progress
Revises: m128_sysconfig_upby_null
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op

revision = "m129_map_crawl_progress"
down_revision = "m128_sysconfig_upby_null"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "map_crawl_progress",
        sa.Column("source", sa.String(20), primary_key=True),
        sa.Column("region_code", sa.String(12), primary_key=True),
        sa.Column("region_name", sa.String(64), nullable=False),
        sa.Column("city_name", sa.String(64), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="done"),
        sa.Column("fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ingested", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_map_crawl_source_status", "map_crawl_progress",
                    ["source", "status"])


def downgrade():
    op.drop_index("ix_map_crawl_source_status", table_name="map_crawl_progress")
    op.drop_table("map_crawl_progress")
