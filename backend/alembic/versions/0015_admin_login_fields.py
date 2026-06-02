"""add username + password_hash to users (运营管理员账号密码登录)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
