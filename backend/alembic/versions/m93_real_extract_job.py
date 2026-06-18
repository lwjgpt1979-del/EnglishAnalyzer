"""真题抽题异步任务 real_extract_job(上传→OCR/拆题→待校对)。带存在性保护。

Revision ID: m93_real_extract_job
Revises: m92_curriculum_gen_job
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m93_real_extract_job"
down_revision = "m92_curriculum_gen_job"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("real_extract_job"):
        op.create_table(
            "real_extract_job",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("source", sa.String(8), nullable=False),
            sa.Column("file_id", sa.String(64), nullable=True),
            sa.Column("image_urls", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="running"),
            sa.Column("parsed", JSONB(), nullable=False, server_default="[]"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_real_extract_job_status", "real_extract_job", ["status"])


def downgrade() -> None:
    if _has("real_extract_job"):
        op.drop_index("ix_real_extract_job_status", table_name="real_extract_job")
        op.drop_table("real_extract_job")
