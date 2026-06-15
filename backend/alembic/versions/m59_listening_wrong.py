"""听力错题归集（§6.4）：listening_wrong_questions 表

精听答错的题目归集，供错题库重练 + 学情。带存在性保护，可重复 upgrade head。

Revision ID: m59_listening_wrong
Revises: m58_user_ban
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m59_listening_wrong"
down_revision = "m58_user_ban"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade() -> None:
    if not _has_table("listening_wrong_questions"):
        op.create_table(
            "listening_wrong_questions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("exercise_id", sa.String(), nullable=False),
            sa.Column("exercise_title", sa.String(), nullable=True),
            sa.Column("question_index", sa.SmallInteger(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("options", JSONB(), nullable=True),
            sa.Column("correct_index", sa.SmallInteger(), nullable=False),
            sa.Column("chosen_index", sa.SmallInteger(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_wrong_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "uix_listening_wrong",
            "listening_wrong_questions",
            ["student_id", "exercise_id", "question_index"], unique=True,
        )


def downgrade() -> None:
    if _has_table("listening_wrong_questions"):
        op.drop_table("listening_wrong_questions")
