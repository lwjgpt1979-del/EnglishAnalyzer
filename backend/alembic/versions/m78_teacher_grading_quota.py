"""老师月度额度配置化（§5.6）：teachers.monthly_grading_quota

月度批改/点评上限的个体覆盖列（NULL=随全局配置 teacher_limits）。
全局默认存 system_configs.teacher_limits，无需建表。带存在性保护。

Revision ID: m78_teacher_grading_quota
Revises: m77_announcements
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m78_teacher_grading_quota"
down_revision = "m77_announcements"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    if "teachers" in _insp().get_table_names() and not _has_col("teachers", "monthly_grading_quota"):
        op.add_column("teachers", sa.Column("monthly_grading_quota", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "teachers" in _insp().get_table_names() and _has_col("teachers", "monthly_grading_quota"):
        op.drop_column("teachers", "monthly_grading_quota")
