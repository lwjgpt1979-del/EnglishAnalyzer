"""reading_question_studied:阅读理解精讲「已精讲」记录(看解析/练同类即算学过)。幂等。

Revision ID: m172_reading_question_studied
Revises: m171_reading_practice_cache
Create Date: 2026-07-16
"""
from alembic import op

revision = "m172_reading_question_studied"
down_revision = "m171_reading_practice_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE IF NOT EXISTS reading_question_studied ("
        "student_id UUID NOT NULL, "
        "question_id UUID NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (student_id, question_id))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reading_studied_student "
        "ON reading_question_studied (student_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS reading_question_studied")
