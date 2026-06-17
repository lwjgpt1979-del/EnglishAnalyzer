"""教材接入 KP-First（R1）：unit_node 单元↔知识节点边。

指向新 knowledge_nodes,与旧 unit_knowledge_points 并存。带存在性保护,可重复 upgrade head。

Revision ID: m84_unit_node
Revises: m83_question_domain
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m84_unit_node"
down_revision = "m83_question_domain"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has(t):
    return t in _insp().get_table_names()


def upgrade() -> None:
    if not _has("unit_node"):
        op.create_table(
            "unit_node",
            sa.Column("unit_id", UUID(as_uuid=True),
                      sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True),
                      sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
            sa.Column("source", sa.String(16), nullable=False, server_default="ai_extract"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_unit_node_node", "unit_node", ["node_id"])


def downgrade() -> None:
    if _has("unit_node"):
        op.drop_table("unit_node")
