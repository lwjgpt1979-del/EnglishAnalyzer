"""teacher_module: add teacher_bind to invite_code_type, create teacher_comments

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 12+ supports ALTER TYPE ADD VALUE inside a transaction.
    op.execute(
        "ALTER TYPE invite_code_type ADD VALUE IF NOT EXISTS 'teacher_bind'"
    )

    op.create_table(
        "teacher_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "wrong_question_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_text", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["wrong_question_id"],
            ["wrong_questions.id"],
            name="fk_teacher_comments_wq",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name="fk_teacher_comments_teacher",
        ),
    )
    op.create_index(
        "ix_teacher_comments_wq_id", "teacher_comments", ["wrong_question_id"]
    )
    op.create_index(
        "ix_teacher_comments_teacher_id", "teacher_comments", ["teacher_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_comments_teacher_id", table_name="teacher_comments")
    op.drop_index("ix_teacher_comments_wq_id", table_name="teacher_comments")
    op.drop_table("teacher_comments")
    # NOTE: PostgreSQL does not support removing enum values.
    # invite_code_type 保留 'teacher_bind' 值。
