"""m216: 语法细目缺教材句时 LLM 示范句全局缓存.

Revision ID: m216_grammar_facet_demo_cache
Revises: m215_student_grammar_facet_pass
"""
from __future__ import annotations

from alembic import op

revision = "m216_grammar_facet_demo_cache"
down_revision = "m215_student_grammar_facet_pass"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS grammar_facet_demo_cache ("
        "input_md5 VARCHAR(32) PRIMARY KEY, "
        "point_name VARCHAR(120) NOT NULL, "
        "facet_name VARCHAR(80) NOT NULL, "
        "sentences JSONB NOT NULL, "
        "zh_hints JSONB, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grammar_facet_demo_cache")
