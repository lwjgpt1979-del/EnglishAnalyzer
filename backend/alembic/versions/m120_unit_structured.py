"""域22:单元结构化解析两张表(语法点+分级句 / 听力考点+句组 / 作文要求+正文)。

「重新生成短文」第一步:LLM 解析单元原文 → curriculum_unit_section(+句子表);
语法点/听力考点 node_id 第二步「关联知识图谱」再填。幂等:表已存在则跳过。

Revision ID: m120_unit_structured
Revises: m119_answer_log_node
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m120_unit_structured"
down_revision = "m119_answer_log_node"
branch_labels = None
depends_on = None


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has("curriculum_unit_section"):
        op.create_table(
            "curriculum_unit_section",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("unit_id", UUID(as_uuid=True),
                      sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("point_name", sa.String(200), nullable=True),
            sa.Column("node_id", UUID(as_uuid=True),
                      sa.ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("node_code", sa.String(64), nullable=True),
            sa.Column("requirement", sa.Text(), nullable=True),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_unit_section_unit", "curriculum_unit_section", ["unit_id", "kind"])

    if not _has("curriculum_unit_section_sentence"):
        op.create_table(
            "curriculum_unit_section_sentence",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("section_id", UUID(as_uuid=True),
                      sa.ForeignKey("curriculum_unit_section.id", ondelete="CASCADE"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("difficulty", sa.Integer(), nullable=True),
            sa.Column("syntax_points", JSONB(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
        op.create_index("ix_unit_section_sentence_section",
                        "curriculum_unit_section_sentence", ["section_id"])


def downgrade() -> None:
    op.drop_table("curriculum_unit_section_sentence")
    op.drop_table("curriculum_unit_section")
