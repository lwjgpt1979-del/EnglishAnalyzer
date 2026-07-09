"""student_kp 加权掌握度计数器:首答对/首答错 + 订正对/订正错。

裸正确率(correct/total)对小样本(3对3=100%)和少量错误误导;改为加权掌握度
(基数下限 10、错罚重、订正回收部分分)。四个计数器独立维护,不动原 practice_count/
wrong_count(仍是总次数,供既有正确率/弱项排序),故其他功能零影响。
掌握度公式见 kp_mastery_service.weighted_mastery。幂等(IF NOT EXISTS)。

Revision ID: m139_student_kp_mastery_counters
Revises: m138_drop_node_resource
Create Date: 2026-07-09
"""
from alembic import op

revision = "m139_student_kp_mastery_counters"
down_revision = "m138_drop_node_resource"
branch_labels = None
depends_on = None

_COLS = ("fa_correct", "fa_wrong", "corrected_count", "redo_wrong_count")


def upgrade():
    for col in _COLS:
        op.execute(
            f"ALTER TABLE student_kp ADD COLUMN IF NOT EXISTS {col} "
            "INTEGER NOT NULL DEFAULT 0"
        )


def downgrade():
    for col in _COLS:
        op.execute(f"ALTER TABLE student_kp DROP COLUMN IF EXISTS {col}")
