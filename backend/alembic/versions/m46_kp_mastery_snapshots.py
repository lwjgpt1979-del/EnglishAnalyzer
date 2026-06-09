"""create kp_mastery_snapshots table (M46)

Revision ID: m46_snapshots
Revises: eea9918c4218
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "m46_snapshots"
down_revision = "eea9918c4218"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kp_mastery_snapshots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("kp_key", sa.Text(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "kp_key", "snapshot_date",
                            name="uq_kp_snapshot_student_kp_date"),
    )
    op.create_index("ix_kp_snapshots_student_kp_date",
                    "kp_mastery_snapshots", ["student_id", "kp_key", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_kp_snapshots_student_kp_date", table_name="kp_mastery_snapshots")
    op.drop_table("kp_mastery_snapshots")
