"""错题中心承接复习(KP-First R3.1):wrong_record 补 SM-2 字段 + 唯一约束。

mastery_source / review_count / easiness_factor / review_interval_days /
next_review_at / last_review_at + 唯一(student_id, q_scope, question_id)供收口 upsert。
带存在性保护。

Revision ID: m86_wrong_record_sm2
Revises: m85_pq_source_check
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = "m86_wrong_record_sm2"
down_revision = "m85_pq_source_check"
branch_labels = None
depends_on = None


def _cols() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("wrong_record")}


def _has_constraint(name: str) -> bool:
    return op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}
    ).first() is not None


def _has_index(name: str) -> bool:
    return op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_class WHERE relname = :n AND relkind = 'i'"), {"n": name}
    ).first() is not None


def upgrade() -> None:
    cols = _cols()
    add = [
        ("mastery_source", sa.Column("mastery_source", sa.String(10), nullable=True)),
        ("review_count", sa.Column("review_count", sa.Integer(), nullable=False, server_default="0")),
        ("easiness_factor", sa.Column("easiness_factor", sa.Numeric(4, 2), nullable=False, server_default="2.50")),
        ("review_interval_days", sa.Column("review_interval_days", sa.Integer(), nullable=False, server_default="1")),
        ("next_review_at", sa.Column("next_review_at", sa.Date(), nullable=True)),
        ("last_review_at", sa.Column("last_review_at", sa.Date(), nullable=True)),
    ]
    for name, col in add:
        if name not in cols:
            op.add_column("wrong_record", col)
    if not _has_index("ix_wrong_record_due"):
        op.create_index("ix_wrong_record_due", "wrong_record", ["student_id", "next_review_at"])
    if not _has_constraint("uix_wrong_record_identity"):
        op.create_unique_constraint(
            "uix_wrong_record_identity", "wrong_record",
            ["student_id", "q_scope", "question_id"],
        )


def downgrade() -> None:
    if _has_constraint("uix_wrong_record_identity"):
        op.drop_constraint("uix_wrong_record_identity", "wrong_record", type_="unique")
    if _has_index("ix_wrong_record_due"):
        op.drop_index("ix_wrong_record_due", "wrong_record")
    cols = _cols()
    for name in ("last_review_at", "next_review_at", "review_interval_days",
                 "easiness_factor", "review_count", "mastery_source"):
        if name in cols:
            op.drop_column("wrong_record", name)
