"""仿真派生真题铁律(KP-First R2.1):platform_question 加 CHECK 约束。

type='sim' 的题必须有源:要么 parent_real_id(派生自真题),要么 is_fallback(显式 KP 直生备选)。
type='real' 不受限。杜绝无源仿真。带存在性保护。

Revision ID: m85_pq_source_check
Revises: m84_unit_node
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = "m85_pq_source_check"
down_revision = "m84_unit_node"
branch_labels = None
depends_on = None

_CK = "ck_platform_question_sim_has_source"


def _has_constraint() -> bool:
    rows = op.get_bind().execute(sa.text(
        "SELECT 1 FROM pg_constraint WHERE conname = :n"
    ), {"n": _CK}).first()
    return rows is not None


def upgrade() -> None:
    if not _has_constraint():
        op.create_check_constraint(
            _CK, "platform_question",
            "type = 'real' OR parent_real_id IS NOT NULL OR is_fallback",
        )


def downgrade() -> None:
    if _has_constraint():
        op.drop_constraint(_CK, "platform_question", type_="check")
