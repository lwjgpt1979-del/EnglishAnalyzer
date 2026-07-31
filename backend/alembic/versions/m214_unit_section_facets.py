"""m214: 单元语法板块双层细目 facets JSONB.

Revision ID: m214_unit_section_facets
Revises: m213_unit_course_text_kg_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m214_unit_section_facets"
down_revision = "m213_unit_course_text_kg_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_unit_section",
        sa.Column("facets", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("curriculum_unit_section", "facets")
