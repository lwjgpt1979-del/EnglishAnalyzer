"""platform_question 加 sim_version:仿真题按"题位(母题/短文组)"累加版本(v1/v2/v3…)。

一个真题卷 → 一套仿真卷;同一母题/短文组反复派生 = 往上累加版本号。

Revision ID: m105_sim_version
Revises: m104_unit_pdf
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "m105_sim_version"
down_revision = "m104_unit_pdf"
branch_labels = None
depends_on = None


def _has_col(c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns("platform_question"))


def upgrade() -> None:
    if not _has_col("sim_version"):
        op.add_column("platform_question", sa.Column("sim_version", sa.SmallInteger(), nullable=True))
    # 按母题分组查"该题位已有最高版本"用
    op.create_index("ix_platform_question_sim_ver", "platform_question",
                    ["parent_real_id", "sim_version"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_platform_question_sim_ver", table_name="platform_question", if_exists=True)
    if _has_col("sim_version"):
        op.drop_column("platform_question", "sim_version")
