"""OCR 手动修正率（§5.5）：wrong_questions.ocr_corrected

用户确认 OCR 结果时若实际改动过识别文本，则置 true，供大盘算手动修正率。
带存在性保护，可重复 upgrade head。

Revision ID: m72_ocr_corrected
Revises: m71_mastery_source
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m72_ocr_corrected"
down_revision = "m71_mastery_source"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    if "wrong_questions" in _insp().get_table_names() and not _has_col("wrong_questions", "ocr_corrected"):
        op.add_column("wrong_questions", sa.Column(
            "ocr_corrected", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    if "wrong_questions" in _insp().get_table_names() and _has_col("wrong_questions", "ocr_corrected"):
        op.drop_column("wrong_questions", "ocr_corrected")
