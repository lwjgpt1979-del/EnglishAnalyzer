"""create student_vocab_candidates table (M50 词力通来源候选词)

Revision ID: m50_vocab_cand
Revises: m49_inst_source
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "m50_vocab_cand"
down_revision = "m49_inst_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_vocab_candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("word_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["vocabulary_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "word_id",
                            name="uix_student_vocab_candidate_student_word"),
    )
    op.create_index("ix_student_vocab_candidates_student",
                    "student_vocab_candidates", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_student_vocab_candidates_student", table_name="student_vocab_candidates")
    op.drop_table("student_vocab_candidates")
