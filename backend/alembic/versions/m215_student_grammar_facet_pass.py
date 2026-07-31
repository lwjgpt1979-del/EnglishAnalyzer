"""m215: 学生单元语法细目闯关过关记录.

Revision ID: m215_student_grammar_facet_pass
Revises: m214_unit_section_facets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "m215_student_grammar_facet_pass"
down_revision = "m214_unit_section_facets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_grammar_facet_pass",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("facet_name", sa.String(80), nullable=False),
        sa.Column(
            "passed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "student_id", "unit_id", "node_id", "facet_name",
            name="uq_student_grammar_facet_pass",
        ),
    )
    op.create_index(
        "ix_sgfp_student_unit_node",
        "student_grammar_facet_pass",
        ["student_id", "unit_id", "node_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sgfp_student_unit_node", table_name="student_grammar_facet_pass")
    op.drop_table("student_grammar_facet_pass")
