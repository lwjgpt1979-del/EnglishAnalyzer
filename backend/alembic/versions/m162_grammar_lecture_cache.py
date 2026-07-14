"""grammar_lecture_cache:个人语法 AI 讲解按语法名全局缓存。幂等。

Revision ID: m162_grammar_lecture_cache
Revises: m161_sgn_source_paper
Create Date: 2026-07-15
"""
from alembic import op

revision = "m162_grammar_lecture_cache"
down_revision = "m161_sgn_source_paper"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS grammar_lecture_cache (
            name_norm VARCHAR(120) PRIMARY KEY,
            display_name VARCHAR(120) NOT NULL,
            sections JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS grammar_lecture_cache")
