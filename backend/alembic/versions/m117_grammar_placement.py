"""R10.6 语法分级测验(CAT 冷启动):grammar_placement_session 会话表。

Revision ID: m117_grammar_placement
Revises: m116_grammar_retention
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m117_grammar_placement"
down_revision = "m116_grammar_retention"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if "grammar_placement_session" not in _tables():
        op.create_table(
            "grammar_placement_session",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("student_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("textbook", sa.String(), nullable=True),
            sa.Column("grade", sa.String(), nullable=True),
            sa.Column("pool_kp_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("asked", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("lo", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("hi", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
            sa.Column("result_priors", JSONB(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )
        op.create_index("ix_gps_student", "grammar_placement_session", ["student_id"])


def downgrade():
    if "grammar_placement_session" in _tables():
        op.drop_index("ix_gps_student", table_name="grammar_placement_session")
        op.drop_table("grammar_placement_session")
