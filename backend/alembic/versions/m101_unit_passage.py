"""单元短文表 curriculum_unit_passages:存每单元析出的 听力脚本/阅读短文/写作范文。

Revision ID: m101_unit_passage
Revises: m100_rc_lt_wr_kp
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "m101_unit_passage"
down_revision = "m100_rc_lt_wr_kp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curriculum_unit_passages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("unit_id", UUID(as_uuid=True),
                  sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),       # 听力|阅读|写作
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_cu_passage_unit", "curriculum_unit_passages", ["unit_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_cu_passage_unit", table_name="curriculum_unit_passages")
    op.drop_table("curriculum_unit_passages")
