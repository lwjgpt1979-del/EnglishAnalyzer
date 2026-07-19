"""users.exam_target:考试目标 junior(中考)|senior(高考),词力通按此出考纲词/短语。幂等。

Revision ID: m178_user_exam_target
Revises: m176_wrong_record_error_type
Create Date: 2026-07-18
"""
from alembic import op

revision = "m178_user_exam_target"
down_revision = "m176_wrong_record_error_type"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS exam_target VARCHAR(8)")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS exam_target")
