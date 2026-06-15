"""多收款主体（渠道无关）：payment_accounts 表 + orders.payment_account_id

支撑主体演进（个体→公司→总公司+地方子公司）与多支付渠道（微信/支付宝/苹果IAP…）：
  新表 payment_accounts：provider + config(JSONB,渠道非密身份) + secret_alias
       （密钥不入库）+ branch_company_id + is_default(部分唯一索引) + is_active
  orders 加列 payment_account_id（下单固化收款主体，退款原路退回）

带存在性保护，全新生产库与已手建开发库均可安全 upgrade head（同 m54/m55）。

Revision ID: m56_payment_accounts
Revises: m55_refund_appeal
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m56_payment_accounts"
down_revision = "m55_refund_appeal"
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
    if not _has_table("payment_accounts"):
        op.create_table(
            "payment_accounts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("subject_type", sa.String(), nullable=False, server_default="company"),
            sa.Column("provider", sa.String(), nullable=False, server_default="wechat"),
            sa.Column("config", JSONB(), nullable=True),
            sa.Column("secret_alias", sa.String(), nullable=True),
            sa.Column("branch_company_id", UUID(as_uuid=True),
                      sa.ForeignKey("branch_companies.id"), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        # is_default=true 仅允许一条
        op.create_index(
            "uix_payment_accounts_default",
            "payment_accounts", ["is_default"], unique=True,
            postgresql_where=sa.text("is_default = true"),
        )

    if not _has_column("orders", "payment_account_id"):
        op.add_column("orders", sa.Column("payment_account_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    if _has_column("orders", "payment_account_id"):
        op.drop_column("orders", "payment_account_id")
    if _has_table("payment_accounts"):
        op.drop_table("payment_accounts")
