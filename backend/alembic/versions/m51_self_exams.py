"""create self_exams table (M51 ProMax自助出卷 5C)

Revision ID: m51_self_exams
Revises: m50_vocab_cand
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m51_self_exams"
down_revision = "m50_vocab_cand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("answering", "done", name="self_exam_status")
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "self_exams",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("status", status, server_default=sa.text("'answering'"), nullable=False),
        sa.Column("question_ids", JSONB(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("weak_kps", JSONB(), nullable=True),
        sa.Column("time_limit_sec", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_self_exams_student", "self_exams", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_self_exams_student", table_name="self_exams")
    op.drop_table("self_exams")
    sa.Enum(name="self_exam_status").drop(op.get_bind(), checkfirst=True)
