"""讲解内容版本快照表 node_resource_version(C1)。append-only,带存在性保护。

Revision ID: m95_nr_version
Revises: m94_region
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m95_nr_version"
down_revision = "m94_region"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("node_resource_version"):
        op.create_table(
            "node_resource_version",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("resource_id", UUID(as_uuid=True),
                      sa.ForeignKey("node_resource.id", ondelete="CASCADE"), nullable=False),
            sa.Column("node_id", UUID(as_uuid=True), nullable=False),
            sa.Column("dimension", sa.String(16), nullable=True),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("content_md", sa.Text(), nullable=True),
            sa.Column("media_url", sa.String(512), nullable=True),
            sa.Column("resource_json", JSONB(), nullable=True),
            sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'manual'")),
            sa.Column("origin_ref", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("created_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
            sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        )
        op.create_index("ix_nrv_resource", "node_resource_version", ["resource_id", "version_no"])
        op.create_index("ix_nrv_node", "node_resource_version", ["node_id"])
        op.create_index("ix_nrv_status", "node_resource_version", ["status"])


def downgrade() -> None:
    if _has("node_resource_version"):
        op.drop_index("ix_nrv_status", table_name="node_resource_version")
        op.drop_index("ix_nrv_node", table_name="node_resource_version")
        op.drop_index("ix_nrv_resource", table_name="node_resource_version")
        op.drop_table("node_resource_version")
