"""平台试卷 platform_paper + platform_question.paper_id/section(整卷上传聚合)。

Revision ID: m96_platform_paper
Revises: m95_nr_version
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m96_platform_paper"
down_revision = "m95_nr_version"
branch_labels = None
depends_on = None


def _has_table(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def _has_col(t, c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns(t))


def upgrade() -> None:
    if not _has_table("platform_paper"):
        op.create_table(
            "platform_paper",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("textbook_version", sa.String(24), nullable=True),
            sa.Column("stage", sa.String(8), nullable=True),
            sa.Column("grade", sa.String(12), nullable=True),
            sa.Column("semester", sa.String(4), nullable=True),
            sa.Column("region_code", sa.String(12), nullable=True),
            sa.Column("region_name", sa.String(64), nullable=True),
            sa.Column("exam_type", sa.String(12), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("meta", JSONB(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_platform_paper_status", "platform_paper", ["status"])

    if not _has_col("platform_question", "paper_id"):
        op.add_column("platform_question", sa.Column(
            "paper_id", UUID(as_uuid=True),
            sa.ForeignKey("platform_paper.id"), nullable=True))
        op.create_index("ix_platform_question_paper", "platform_question", ["paper_id"])
    if not _has_col("platform_question", "section"):
        op.add_column("platform_question", sa.Column("section", sa.String(24), nullable=True))


def downgrade() -> None:
    if _has_col("platform_question", "section"):
        op.drop_column("platform_question", "section")
    if _has_col("platform_question", "paper_id"):
        op.drop_index("ix_platform_question_paper", table_name="platform_question")
        op.drop_column("platform_question", "paper_id")
    if _has_table("platform_paper"):
        op.drop_index("ix_platform_paper_status", table_name="platform_paper")
        op.drop_table("platform_paper")
