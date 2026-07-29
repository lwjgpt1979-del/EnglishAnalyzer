"""user_paper_sections.in_cloze_intensive + 完形精讲缓存/studied 表。幂等。

Revision ID: m207_cloze_intensive
Revises: m206_paper_q_explain_cache
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op

revision = "m207_cloze_intensive"
down_revision = "m206_paper_q_explain_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_paper_sections "
        "ADD COLUMN IF NOT EXISTS in_cloze_intensive BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS cloze_analysis_cache ("
        "q_md5 VARCHAR(32) PRIMARY KEY, "
        "analysis JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS cloze_practice_cache ("
        "cache_md5 VARCHAR(32) PRIMARY KEY, "
        "questions JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS cloze_question_studied ("
        "student_id UUID NOT NULL, "
        "question_id UUID NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (student_id, question_id))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cloze_question_studied")
    op.execute("DROP TABLE IF EXISTS cloze_practice_cache")
    op.execute("DROP TABLE IF EXISTS cloze_analysis_cache")
    op.execute("ALTER TABLE user_paper_sections DROP COLUMN IF EXISTS in_cloze_intensive")
