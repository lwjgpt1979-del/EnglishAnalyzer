"""m213: 单元粘贴原文 course_text + section 来源 + 结构化解析缓存.

Revision ID: m213_unit_course_text_kg_source
Revises: m212_option_vocab_pipeline_job
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m213_unit_course_text_kg_source"
down_revision = "m212_option_vocab_pipeline_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_units",
        sa.Column("course_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "curriculum_unit_section",
        sa.Column("extract_source", sa.String(16), nullable=True),
    )
    op.create_table(
        "unit_structured_parse_cache",
        sa.Column("content_md5", sa.String(32), primary_key=True),
        sa.Column("result", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("unit_structured_parse_cache")
    op.drop_column("curriculum_unit_section", "extract_source")
    op.drop_column("curriculum_units", "course_text")
