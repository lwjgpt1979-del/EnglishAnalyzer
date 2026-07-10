"""R8.1:退役旧掌握台账 student_kp_mastery + 日快照 kp_mastery_snapshots。

掌握账已统一到 student_kp(node):读侧(诊断/学习计划/老师/家长/激励/机构)已切,
写侧 upsert_mastery 经 match_kp 只写 student_kp,回归预警改从 answer_log 重放。
两表已无 app 读写,删表。幂等(IF EXISTS)。

Revision ID: m140_drop_kp_mastery_ledger
Revises: m139_student_kp_mastery_counters
Create Date: 2026-07-10
"""
from alembic import op

revision = "m140_drop_kp_mastery_ledger"
down_revision = "m139_student_kp_mastery_counters"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS kp_mastery_snapshots")
    op.execute("DROP TABLE IF EXISTS student_kp_mastery")


def downgrade():
    # 旧台账已退役,不恢复(如需回滚请从 m139 之前的建表迁移重建)。
    pass
