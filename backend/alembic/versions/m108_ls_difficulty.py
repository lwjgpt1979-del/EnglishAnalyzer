"""long_sentence 加 difficulty:句法复杂度难度分 0–100(spaCy 依存:从句数/树深/MDD/词数)。

Revision ID: m108_ls_difficulty
Revises: m107_ls_favorite
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "m108_ls_difficulty"
down_revision = "m107_ls_favorite"
branch_labels = None
depends_on = None


def _has_col(c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns("long_sentence"))


def upgrade():
    if not _has_col("difficulty"):
        op.add_column("long_sentence", sa.Column("difficulty", sa.Integer(), nullable=True))
        op.create_index("ix_long_sentence_difficulty", "long_sentence", ["difficulty"])


def downgrade():
    if _has_col("difficulty"):
        op.drop_index("ix_long_sentence_difficulty", table_name="long_sentence")
        op.drop_column("long_sentence", "difficulty")
