"""vocab_image_report:学生「图不对」投票(去重+每人每日限流)。P3 ②①。幂等。

Revision ID: m175_vocab_image_report
Revises: m174_vocab_media_report_count
Create Date: 2026-07-17
"""
from alembic import op

revision = "m175_vocab_image_report"
down_revision = "m174_vocab_media_report_count"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE IF NOT EXISTS vocab_image_report ("
        "word_id UUID NOT NULL, "
        "student_id UUID NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (word_id, student_id))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vocab_image_report_student_day "
        "ON vocab_image_report (student_id, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_image_report")
