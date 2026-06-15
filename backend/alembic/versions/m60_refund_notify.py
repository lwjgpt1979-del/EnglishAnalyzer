"""退款异步对账：refund_records 加 out_refund_no / wx_refund_status

out_refund_no 用于匹配微信退款结果通知；wx_refund_status 存通知回的原始状态对账。
带存在性保护，可重复 upgrade head。

Revision ID: m60_refund_notify
Revises: m59_listening_wrong
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "m60_refund_notify"
down_revision = "m59_listening_wrong"
branch_labels = None
depends_on = None


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("refund_records", "out_refund_no"):
        op.add_column("refund_records", sa.Column("out_refund_no", sa.String(), nullable=True))
        op.create_index("ix_refund_records_out_refund_no", "refund_records", ["out_refund_no"])
    if not _has_column("refund_records", "wx_refund_status"):
        op.add_column("refund_records", sa.Column("wx_refund_status", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("refund_records", "wx_refund_status"):
        op.drop_column("refund_records", "wx_refund_status")
    if _has_column("refund_records", "out_refund_no"):
        op.drop_column("refund_records", "out_refund_no")
