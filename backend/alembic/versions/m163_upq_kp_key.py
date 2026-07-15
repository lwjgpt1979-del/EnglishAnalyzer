"""user_paper_questions 加 kp_key(单题归类名,判语法/词汇)。幂等。

Revision ID: m163_upq_kp_key
Revises: m162_grammar_lecture_cache
Create Date: 2026-07-15
"""
from alembic import op

revision = "m163_upq_kp_key"
down_revision = "m162_grammar_lecture_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_paper_questions ADD COLUMN IF NOT EXISTS kp_key VARCHAR(120)")


def downgrade():
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS kp_key")
