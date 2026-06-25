"""R9.6 优先学:student_vocab_candidates 加 priority(学生主动优先学的级别)。

Revision ID: m114_vocab_pin_priority
Revises: m113_vocab_probes
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "m114_vocab_pin_priority"
down_revision = "m113_vocab_probes"
branch_labels = None
depends_on = None


def _cols(t):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(t)}


def upgrade():
    if "priority" not in _cols("student_vocab_candidates"):
        op.add_column("student_vocab_candidates",
                      sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
        op.create_index("ix_svc_student_priority", "student_vocab_candidates", ["student_id", "priority"])


def downgrade():
    if "priority" in _cols("student_vocab_candidates"):
        op.drop_index("ix_svc_student_priority", table_name="student_vocab_candidates")
        op.drop_column("student_vocab_candidates", "priority")
