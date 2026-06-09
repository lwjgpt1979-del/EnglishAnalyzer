"""Add SM-2 spaced-repetition fields to wrong_questions (M36).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wrong_questions",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wrong_questions",
        sa.Column("easiness_factor", sa.Numeric(precision=4, scale=2), nullable=False, server_default="2.50"),
    )
    op.add_column(
        "wrong_questions",
        sa.Column("review_interval_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "wrong_questions",
        sa.Column("next_review_at", sa.Date(), nullable=True),
    )
    op.add_column(
        "wrong_questions",
        sa.Column("last_review_at", sa.Date(), nullable=True),
    )
    # 创建索引：按学生 + 下次复习日期快速查今日队列
    op.create_index(
        "ix_wrong_questions_student_next_review",
        "wrong_questions",
        ["student_id", "next_review_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wrong_questions_student_next_review", table_name="wrong_questions")
    op.drop_column("wrong_questions", "last_review_at")
    op.drop_column("wrong_questions", "next_review_at")
    op.drop_column("wrong_questions", "review_interval_days")
    op.drop_column("wrong_questions", "easiness_factor")
    op.drop_column("wrong_questions", "review_count")
