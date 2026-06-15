"""用户封禁（§5.3.1）：users 加 ban_reason / banned_until / banned_at

is_active=False 即封禁；banned_until 空=永久，有值=临时（到期鉴权时自动解封）。
带存在性保护，可安全重复 upgrade head（同 m54~m57）。

Revision ID: m58_user_ban
Revises: m57_payment_secrets_enc
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "m58_user_ban"
down_revision = "m57_payment_secrets_enc"
branch_labels = None
depends_on = None


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("users", "ban_reason"):
        op.add_column("users", sa.Column("ban_reason", sa.Text(), nullable=True))
    if not _has_column("users", "banned_until"):
        op.add_column("users", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("users", "banned_at"):
        op.add_column("users", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("banned_at", "banned_until", "ban_reason"):
        if _has_column("users", col):
            op.drop_column("users", col)
