"""机构套餐（§9.1/§5.6）：institutions 加 package_tier + 配额 override 列

档位定义与配额默认值全在 system_configs.institution_packages（配置驱动，非枚举）；
机构维度仅存所选档位 + 可选覆盖。带存在性保护，可重复 upgrade head。

Revision ID: m81_institution_package
Revises: m80_perf_indexes
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m81_institution_package"
down_revision = "m80_perf_indexes"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c["name"] for c in _insp().get_columns(table)}


_COLS = {
    "package_tier": sa.Column("package_tier", sa.String(20), nullable=True),
    "teacher_seats_override": sa.Column("teacher_seats_override", sa.Integer(), nullable=True),
    "paper_pool_override": sa.Column("paper_pool_override", sa.Integer(), nullable=True),
    "grading_pool_override": sa.Column("grading_pool_override", sa.Integer(), nullable=True),
}


def upgrade() -> None:
    if "institutions" not in _insp().get_table_names():
        return
    for name, col in _COLS.items():
        if not _has_col("institutions", name):
            op.add_column("institutions", col)


def downgrade() -> None:
    if "institutions" not in _insp().get_table_names():
        return
    for name in _COLS:
        if _has_col("institutions", name):
            op.drop_column("institutions", name)
