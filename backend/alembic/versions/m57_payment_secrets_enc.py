"""payment_accounts 加 secrets_enc（加密存库的渠道密钥，明文不落库）

后台 UI 录入密钥 → AES-256-GCM 加密 → 存 secrets_enc；主密钥(KEK)在 env。
解决多主体/多渠道密钥全堆 env 不可管理的问题。

带存在性保护，可安全重复 upgrade head（同 m54~m56）。

Revision ID: m57_payment_secrets_enc
Revises: m56_payment_accounts
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m57_payment_secrets_enc"
down_revision = "m56_payment_accounts"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_column(table: str, col: str) -> bool:
    if table not in _insp().get_table_names():
        return False
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    if not _has_column("payment_accounts", "secrets_enc"):
        op.add_column("payment_accounts", sa.Column("secrets_enc", JSONB(), nullable=True))


def downgrade() -> None:
    if _has_column("payment_accounts", "secrets_enc"):
        op.drop_column("payment_accounts", "secrets_enc")
