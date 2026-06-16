"""错题复盘率拆分（§5.5）：wrong_questions.mastery_source

记录掌握来源 review(复盘验证通过) / manual(手动标记)，供大盘拆分复盘率。
带存在性保护，可重复 upgrade head。

Revision ID: m71_mastery_source
Revises: m70_acquisition_channel
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m71_mastery_source"
down_revision = "m70_acquisition_channel"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    if "wrong_questions" in _insp().get_table_names() and not _has_col("wrong_questions", "mastery_source"):
        op.add_column("wrong_questions", sa.Column("mastery_source", sa.String(10), nullable=True))


def downgrade() -> None:
    if "wrong_questions" in _insp().get_table_names() and _has_col("wrong_questions", "mastery_source"):
        op.drop_column("wrong_questions", "mastery_source")
