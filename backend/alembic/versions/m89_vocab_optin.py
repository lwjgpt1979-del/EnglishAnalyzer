"""通用词库 opt-in(KP-First R5 收尾):student_vocab_settings 加 include_general_vocab +
general_vocab_list_id。带存在性保护。

Revision ID: m89_vocab_optin
Revises: m88_node_resource
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m89_vocab_optin"
down_revision = "m88_node_resource"
branch_labels = None
depends_on = None


def _cols():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("student_vocab_settings")}


def upgrade() -> None:
    cols = _cols()
    if "include_general_vocab" not in cols:
        op.add_column("student_vocab_settings",
                      sa.Column("include_general_vocab", sa.Boolean(), nullable=False, server_default="false"))
    if "general_vocab_list_id" not in cols:
        op.add_column("student_vocab_settings",
                      sa.Column("general_vocab_list_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    cols = _cols()
    if "general_vocab_list_id" in cols:
        op.drop_column("student_vocab_settings", "general_vocab_list_id")
    if "include_general_vocab" in cols:
        op.drop_column("student_vocab_settings", "include_general_vocab")
