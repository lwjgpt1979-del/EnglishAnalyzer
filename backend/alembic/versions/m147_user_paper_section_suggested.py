"""user_paper_sections 加 is_suggested(AI 建议分类标记,学生可改)。幂等。

Revision ID: m147_ups_suggested
Revises: m146_user_paper_sections
Create Date: 2026-07-08
"""
from alembic import op

revision = "m147_ups_suggested"
down_revision = "m146_user_paper_sections"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_paper_sections ADD COLUMN IF NOT EXISTS is_suggested BOOLEAN NOT NULL DEFAULT false")


def downgrade():
    op.execute("ALTER TABLE user_paper_sections DROP COLUMN IF EXISTS is_suggested")
