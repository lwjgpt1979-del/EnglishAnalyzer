"""教材生成异步任务 curriculum_gen_job(分单元存下、后台逐单元生成、可查进度)。带存在性保护。

Revision ID: m92_curriculum_gen_job
Revises: m91_pending_kp_content
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m92_curriculum_gen_job"
down_revision = "m91_pending_kp_content"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("curriculum_gen_job"):
        op.create_table(
            "curriculum_gen_job",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("source", sa.String(12), nullable=False, server_default="pdf"),  # pdf|semester
            sa.Column("file_id", sa.String(64), nullable=True),
            sa.Column("textbook_version", sa.String(64), nullable=False),
            sa.Column("grade", sa.String(32), nullable=False),
            sa.Column("semester", sa.String(8), nullable=False),
            sa.Column("content_status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("status", sa.String(12), nullable=False, server_default="running"),  # running|done|failed
            sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("segments", JSONB(), nullable=False),   # 待生成单元 [{unit_no,start_page,end_page,detected_title}]
            sa.Column("results", JSONB(), nullable=False, server_default="[]"),  # 各单元结果
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_curriculum_gen_job_status", "curriculum_gen_job", ["status"])
        op.create_index("ix_curriculum_gen_job_book", "curriculum_gen_job",
                        ["textbook_version", "grade", "semester"])


def downgrade() -> None:
    if _has("curriculum_gen_job"):
        op.drop_index("ix_curriculum_gen_job_book", table_name="curriculum_gen_job")
        op.drop_index("ix_curriculum_gen_job_status", table_name="curriculum_gen_job")
        op.drop_table("curriculum_gen_job")
