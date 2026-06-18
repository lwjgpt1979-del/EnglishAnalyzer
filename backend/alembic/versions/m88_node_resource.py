"""知识节点资源（KP-First R6.1）：node_resource 通用资源表挂 knowledge_nodes。

lecture/video/example/essay/mindmap 多类型;lecture 每维度唯一(其它 dimension=null 可多条)。
带存在性保护。

Revision ID: m88_node_resource
Revises: m87_vocab_kg
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m88_node_resource"
down_revision = "m87_vocab_kg"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("node_resource"):
        op.create_table(
            "node_resource",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True),
                      sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("resource_type", sa.String(16), nullable=False),
            sa.Column("dimension", sa.String(16), nullable=True),
            sa.Column("title", sa.String(200), nullable=True),
            sa.Column("content_md", sa.Text(), nullable=True),
            sa.Column("media_url", sa.String(512), nullable=True),
            sa.Column("resource_json", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("generated_by", sa.String(16), nullable=False, server_default="manual"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("node_id", "resource_type", "dimension", name="uix_node_resource_identity"),
        )
        op.create_index("ix_node_resource_node_type", "node_resource", ["node_id", "resource_type"])
        op.create_index("ix_node_resource_status", "node_resource", ["status"])


def downgrade() -> None:
    if _has("node_resource"):
        op.drop_table("node_resource")
