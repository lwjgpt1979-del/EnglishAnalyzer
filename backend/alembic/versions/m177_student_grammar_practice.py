"""student_grammar_node 加练习痕迹字段(自建语法已学/最近成绩)

自建语法无图谱 node、无 BKT 四维掌握;用「练一练」痕迹记 studied + 最近一轮成绩。

Revision ID: m177_student_grammar_practice
Revises: m146_vocab_item_exam_freq
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision = "m177_student_grammar_practice"
down_revision = "m146_vocab_item_exam_freq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等:活跃 alembic 树被并行会话分叉成多头,本迁移曾直接以 DDL 落库;
    # 将来 head 合并跑到这条时 IF NOT EXISTS 保证无害 no-op。
    op.execute("ALTER TABLE student_grammar_node ADD COLUMN IF NOT EXISTS studied_at TIMESTAMPTZ")
    op.execute("ALTER TABLE student_grammar_node ADD COLUMN IF NOT EXISTS last_correct INTEGER")
    op.execute("ALTER TABLE student_grammar_node ADD COLUMN IF NOT EXISTS last_total INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE student_grammar_node DROP COLUMN IF EXISTS last_total")
    op.execute("ALTER TABLE student_grammar_node DROP COLUMN IF EXISTS last_correct")
    op.execute("ALTER TABLE student_grammar_node DROP COLUMN IF EXISTS studied_at")
