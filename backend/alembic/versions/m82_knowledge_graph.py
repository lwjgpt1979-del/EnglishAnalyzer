"""知识图谱骨架（KP-First 重构 R0.1）：knowledge_nodes / aliases / relations / kp_candidates

多轴知识节点 + 别名归一 + 节点关系 + 候选审核。与现有 knowledge_points 并存，不动旧表。
带存在性保护，可重复 upgrade head。

Revision ID: m82_knowledge_graph
Revises: m81_institution_package
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m82_knowledge_graph"
down_revision = "m81_institution_package"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has(t):
    return t in _insp().get_table_names()


def upgrade() -> None:
    if not _has("knowledge_nodes"):
        op.create_table(
            "knowledge_nodes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("axis", sa.String(12), nullable=False),
            sa.Column("node_kind", sa.String(32), nullable=True),
            sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("code", sa.String(64), nullable=False, unique=True),
            sa.Column("applicable_stages", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="active"),
            sa.Column("source", sa.String(16), nullable=False, server_default="seed"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_knowledge_nodes_axis_parent", "knowledge_nodes", ["axis", "parent_id"])
        op.create_index("ix_knowledge_nodes_status", "knowledge_nodes", ["status"])
    if not _has("knowledge_node_aliases"):
        op.create_table(
            "knowledge_node_aliases",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=False),
            sa.Column("alias", sa.String(120), nullable=False),
            sa.Column("alias_norm", sa.String(120), nullable=False, unique=True),
            sa.Column("source", sa.String(12), nullable=False, server_default="seed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_node_aliases_node", "knowledge_node_aliases", ["node_id"])
    if not _has("knowledge_node_relations"):
        op.create_table(
            "knowledge_node_relations",
            sa.Column("from_node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
            sa.Column("to_node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
            sa.Column("relation", sa.String(16), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has("kp_candidates"):
        op.create_table(
            "kp_candidates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("raw_name", sa.String(120), nullable=False),
            sa.Column("name_norm", sa.String(120), nullable=False),
            sa.Column("suggested_axis", sa.String(12), nullable=True),
            sa.Column("suggested_stage", sa.String(8), nullable=True),
            sa.Column("occur_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("context_sample", JSONB(), nullable=True),
            sa.Column("source_type", sa.String(24), nullable=True),
            sa.Column("source_ref", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
            sa.Column("merged_into_node_id", UUID(as_uuid=True), nullable=True),
            sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("name_norm", "suggested_axis", name="uix_kp_candidate_norm_axis"),
        )
        op.create_index("ix_kp_candidates_status", "kp_candidates", ["status", "occur_count"])


def downgrade() -> None:
    for t in ("kp_candidates", "knowledge_node_relations", "knowledge_node_aliases", "knowledge_nodes"):
        if _has(t):
            op.drop_table(t)
