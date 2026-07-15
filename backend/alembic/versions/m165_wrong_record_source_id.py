"""wrong_record.source_id(来源实体id,供「回到错题来源」跳转)。幂等。

Revision ID: m165_wrong_record_source_id
Revises: m164_wrong_record_denorm
Create Date: 2026-07-15
"""
from alembic import op

revision = "m165_wrong_record_source_id"
down_revision = "m164_wrong_record_denorm"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS source_id UUID")

def downgrade():
    op.execute("ALTER TABLE wrong_record DROP COLUMN IF EXISTS source_id")
