"""单元短文↔考点关联表 unit_passage_kp(听力→lt/阅读→rc/写作→wr)。

Revision ID: m102_passage_kp
Revises: m101_unit_passage
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "m102_passage_kp"
down_revision = "m101_unit_passage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unit_passage_kp",
        sa.Column("passage_id", UUID(as_uuid=True),
                  sa.ForeignKey("curriculum_unit_passages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("unit_passage_kp")
