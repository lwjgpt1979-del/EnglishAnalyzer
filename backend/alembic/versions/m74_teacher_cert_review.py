"""老师认证审核增强（§5.8）：teachers 认领/驳回原因/时间戳列

带存在性保护，可重复 upgrade head。

Revision ID: m74_teacher_cert_review
Revises: m73_sensitive_words
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m74_teacher_cert_review"
down_revision = "m73_sensitive_words"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


_COLS = {
    "cert_submitted_at": sa.Column("cert_submitted_at", sa.DateTime(timezone=True), nullable=True),
    "cert_claimed_by": sa.Column("cert_claimed_by", UUID(as_uuid=True), nullable=True),
    "cert_claimed_at": sa.Column("cert_claimed_at", sa.DateTime(timezone=True), nullable=True),
    "cert_reject_reason": sa.Column("cert_reject_reason", sa.Text(), nullable=True),
    "cert_reviewed_at": sa.Column("cert_reviewed_at", sa.DateTime(timezone=True), nullable=True),
}


def upgrade() -> None:
    if "teachers" not in _insp().get_table_names():
        return
    for name, col in _COLS.items():
        if not _has_col("teachers", name):
            op.add_column("teachers", col)


def downgrade() -> None:
    if "teachers" not in _insp().get_table_names():
        return
    for name in _COLS:
        if _has_col("teachers", name):
            op.drop_column("teachers", name)
