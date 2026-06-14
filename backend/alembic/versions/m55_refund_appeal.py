"""退款 / 申诉系统 P1：orders 退款列 + payment_confirm_logs 表 + refund_records 申诉列

§4.5/4.6 退款规则引擎与支付确认举证落地：
  orders 加列：refund_status / appeal_status / is_promotional / total_days /
               payment_confirm_log_id（状态码用 VARCHAR，不建 PG 枚举）
  新表：payment_confirm_logs（支付前合规确认留存，举证用）
  refund_records 加列：appeal_type / state_code / evidence_urls / reviewed_at

每个对象带存在性保护，全新生产库与已手建开发库均可安全 upgrade head（同 m54）。

Revision ID: m55_refund_appeal
Revises: m54_entitlement_vocab_essay
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m55_refund_appeal"
down_revision = "m54_entitlement_vocab_essay"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names()


def _has_column(table: str, col: str) -> bool:
    if not _has_table(table):
        return False
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    # ---- orders 退款/申诉列 ----
    if not _has_column("orders", "refund_status"):
        op.add_column("orders", sa.Column(
            "refund_status", sa.String(), nullable=False, server_default="NONE"))
    if not _has_column("orders", "appeal_status"):
        op.add_column("orders", sa.Column(
            "appeal_status", sa.String(), nullable=False, server_default="NONE"))
    if not _has_column("orders", "is_promotional"):
        op.add_column("orders", sa.Column(
            "is_promotional", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if not _has_column("orders", "total_days"):
        op.add_column("orders", sa.Column("total_days", sa.Integer(), nullable=True))
    if not _has_column("orders", "payment_confirm_log_id"):
        op.add_column("orders", sa.Column(
            "payment_confirm_log_id", UUID(as_uuid=True), nullable=True))

    # ---- payment_confirm_logs 表 ----
    if not _has_table("payment_confirm_logs"):
        op.create_table(
            "payment_confirm_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("order_id", UUID(as_uuid=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
            sa.Column("ip_address", sa.String(), nullable=True),
            sa.Column("device_id", sa.String(), nullable=True),
            sa.Column("session_id", sa.String(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("checkbox_refund_policy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("checkbox_digital_service", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("plan_snapshot", JSONB(), nullable=True),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "ix_payment_confirm_logs_user",
            "payment_confirm_logs", ["user_id", "created_at"],
        )

    # ---- refund_records 申诉/决策树列 ----
    if not _has_column("refund_records", "appeal_type"):
        op.add_column("refund_records", sa.Column("appeal_type", sa.String(), nullable=True))
    if not _has_column("refund_records", "state_code"):
        op.add_column("refund_records", sa.Column("state_code", sa.String(), nullable=True))
    if not _has_column("refund_records", "evidence_urls"):
        op.add_column("refund_records", sa.Column("evidence_urls", JSONB(), nullable=True))
    if not _has_column("refund_records", "reviewed_at"):
        op.add_column("refund_records", sa.Column(
            "reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("reviewed_at", "evidence_urls", "state_code", "appeal_type"):
        if _has_column("refund_records", col):
            op.drop_column("refund_records", col)
    if _has_table("payment_confirm_logs"):
        op.drop_table("payment_confirm_logs")
    for col in ("payment_confirm_log_id", "total_days", "is_promotional",
                "appeal_status", "refund_status"):
        if _has_column("orders", col):
            op.drop_column("orders", col)
