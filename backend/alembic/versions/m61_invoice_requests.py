"""发票申请记录（§5.4）：invoice_requests 表

应用内仅做开票申请 + 状态管理（真实发票由税控/电子发票服务商开具）。
开票方=订单收款主体(payment_account_id 固化)，适配主体演进。
带存在性保护，可重复 upgrade head。

Revision ID: m61_invoice_requests
Revises: m60_refund_notify
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m61_invoice_requests"
down_revision = "m60_refund_notify"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade() -> None:
    if not _has_table("invoice_requests"):
        op.create_table(
            "invoice_requests",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("order_id", UUID(as_uuid=True), nullable=False),
            sa.Column("payment_account_id", UUID(as_uuid=True), nullable=True),
            sa.Column("title_type", sa.String(), nullable=False, server_default="personal"),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("tax_no", sa.String(), nullable=True),
            sa.Column("amount_fen", sa.Integer(), nullable=False),
            sa.Column("content", sa.String(), nullable=True),
            sa.Column("email", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("invoice_no", sa.String(), nullable=True),
            sa.Column("invoice_url", sa.String(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("issued_by", UUID(as_uuid=True), nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index("ix_invoice_requests_user", "invoice_requests", ["user_id", "created_at"])
        op.create_index("ix_invoice_requests_status", "invoice_requests", ["status", "created_at"])
        # 同一订单仅一条有效开票申请（驳回后可重申，故不设唯一约束，由服务层控制）


def downgrade() -> None:
    if _has_table("invoice_requests"):
        op.drop_table("invoice_requests")
