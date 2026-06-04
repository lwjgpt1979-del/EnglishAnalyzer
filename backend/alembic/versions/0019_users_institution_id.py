"""users.institution_id：机构管理员 ↔ 机构绑定键（D-120）

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_institution_id", "users", "institutions",
        ["institution_id"], ["id"],
    )
    op.create_index("ix_users_institution_id", "users", ["institution_id"])


def downgrade() -> None:
    op.drop_index("ix_users_institution_id", table_name="users")
    op.drop_constraint("fk_users_institution_id", "users", type_="foreignkey")
    op.drop_column("users", "institution_id")
