"""m212: option_vocab_pipeline_job 落库(批量入统计可查历史 / 续跑)。

Revision ID: m212_option_vocab_pipeline_job
Revises: m211_vocab_question_link_kind_roles
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m212_option_vocab_pipeline_job"
down_revision = "m211_vocab_question_link_kind_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_vocab_pipeline_job",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("region_code", sa.String(12), nullable=True),
        sa.Column("region_name", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("types", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("paper_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("done", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("adopted", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("suggested", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("concurrency", sa.Integer, nullable=False, server_default=sa.text("6")),
        sa.Column("auto_adopt", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("force_suggest", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("logs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("admin_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_option_vocab_pipeline_job_created",
        "option_vocab_pipeline_job",
        ["created_at"],
    )
    op.create_index(
        "ix_option_vocab_pipeline_job_status",
        "option_vocab_pipeline_job",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_option_vocab_pipeline_job_status", table_name="option_vocab_pipeline_job")
    op.drop_index("ix_option_vocab_pipeline_job_created", table_name="option_vocab_pipeline_job")
    op.drop_table("option_vocab_pipeline_job")
