"""long_sentence 加定位字段(教材版/学段/年级/学期/单元/exam_type)+ 学生独立长难句表。

平台库带定位:教材→单元,普通真题→年级+上下,中考/高考真题→学段。
学生长难句拆到独立表 student_long_sentence(学生量大、重效率,本人可见)。

Revision ID: m109_ls_locate_student
Revises: m108_ls_difficulty
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m109_ls_locate_student"
down_revision = "m108_ls_difficulty"
branch_labels = None
depends_on = None

_COLS = [
    ("textbook_version", sa.String(64)),
    ("stage", sa.String(8)),
    ("grade", sa.String(32)),
    ("semester", sa.String(8)),
    ("unit_id", UUID(as_uuid=True)),
    ("exam_type", sa.String(12)),
]


def _has_col(table, c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns(table))


def _has_table(t):
    return sa.inspect(op.get_bind()).has_table(t)


def upgrade():
    for name, typ in _COLS:
        if not _has_col("long_sentence", name):
            op.add_column("long_sentence", sa.Column(name, typ, nullable=True))
    op.create_index("ix_long_sentence_locate", "long_sentence",
                    ["textbook_version", "grade", "semester"], if_not_exists=True)

    if not _has_table("student_long_sentence"):
        op.create_table(
            "student_long_sentence",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
            sa.Column("source_question_id", UUID(as_uuid=True), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("analysis_json", sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column("difficulty", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'published'")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_student_long_sentence_owner", "student_long_sentence", ["owner_id", "status"])
        op.create_index("ix_student_long_sentence_srcq", "student_long_sentence", ["source_question_id"])


def downgrade():
    if _has_table("student_long_sentence"):
        op.drop_table("student_long_sentence")
    op.drop_index("ix_long_sentence_locate", table_name="long_sentence", if_exists=True)
    for name, _ in _COLS:
        if _has_col("long_sentence", name):
            op.drop_column("long_sentence", name)
