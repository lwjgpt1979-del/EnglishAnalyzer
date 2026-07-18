"""wrong_record.error_type:错题复习标注的错因类型(错因画像)。幂等。

Revision ID: m176_wrong_record_error_type
Revises: m175_vocab_image_report
Create Date: 2026-07-18
"""
from alembic import op

revision = "m176_wrong_record_error_type"
down_revision = "m175_vocab_image_report"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS error_type VARCHAR(12)")


def downgrade():
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS error_type")
