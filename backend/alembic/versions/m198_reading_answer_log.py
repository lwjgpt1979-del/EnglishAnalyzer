"""作业阅读题·主动作答留痕(reading_answer_log)——P3「阅读理解学情统计」。

作业阅读题的 is_wrong 多为空(OCR 抓不到卷面圈选的 A/B/C/D)。学生在精讲里主动
作答一次 → 记 is_correct;留痕、可重做多次(不覆盖原 OCR 值)。读后小结优先取
每题最新一次作答,回落 is_wrong。方案② 独立表。幂等。

Revision ID: m198_reading_answer_log
Revises: m197_reading_skill
Create Date: 2026-07-25
"""
from alembic import op

revision = "m198_reading_answer_log"
down_revision = "m197_reading_skill"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS reading_answer_log (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL,
            question_id UUID NOT NULL,
            chosen VARCHAR(8),
            is_correct BOOLEAN,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # 取某生某题「最新一次」作答:按 (student, question, created_at desc)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ral_student_question "
        "ON reading_answer_log (student_id, question_id, created_at DESC)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_ral_student_question")
    op.execute("DROP TABLE IF EXISTS reading_answer_log")
