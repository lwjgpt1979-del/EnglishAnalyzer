"""语法精讲目标挂来源题:student_kp_target / student_grammar_node 加 source_question_id。

同 KP 多题可各挂一条(D1 按原题切点);无题的旧目标仍用 (student,node)/(student,name_norm) 唯一。

Revision ID: m202_grammar_source_question
Revises: m201_upq_options
Create Date: 2026-07-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m202_grammar_source_question"
down_revision = "m201_upq_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE student_kp_target ADD COLUMN IF NOT EXISTS source_question_id UUID")
    op.execute("ALTER TABLE student_grammar_node ADD COLUMN IF NOT EXISTS source_question_id UUID")
    # 替换全局唯一 → 分有无题的部分唯一索引
    op.execute("ALTER TABLE student_kp_target DROP CONSTRAINT IF EXISTS uix_student_kp_target")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_skt_no_q "
        "ON student_kp_target (student_id, node_id) WHERE source_question_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_skt_with_q "
        "ON student_kp_target (student_id, node_id, source_question_id) "
        "WHERE source_question_id IS NOT NULL"
    )
    op.execute("ALTER TABLE student_grammar_node DROP CONSTRAINT IF EXISTS uix_student_grammar_node")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_sgn_no_q "
        "ON student_grammar_node (student_id, name_norm) WHERE source_question_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uix_sgn_with_q "
        "ON student_grammar_node (student_id, name_norm, source_question_id) "
        "WHERE source_question_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_skt_source_q ON student_kp_target (source_question_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sgn_source_q ON student_grammar_node (source_question_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sgn_source_q")
    op.execute("DROP INDEX IF EXISTS ix_skt_source_q")
    op.execute("DROP INDEX IF EXISTS uix_sgn_with_q")
    op.execute("DROP INDEX IF EXISTS uix_sgn_no_q")
    op.execute("DROP INDEX IF EXISTS uix_skt_with_q")
    op.execute("DROP INDEX IF EXISTS uix_skt_no_q")
    op.execute(
        "ALTER TABLE student_grammar_node "
        "ADD CONSTRAINT uix_student_grammar_node UNIQUE (student_id, name_norm)"
    )
    op.execute(
        "ALTER TABLE student_kp_target "
        "ADD CONSTRAINT uix_student_kp_target UNIQUE (student_id, node_id)"
    )
    op.execute("ALTER TABLE student_grammar_node DROP COLUMN IF EXISTS source_question_id")
    op.execute("ALTER TABLE student_kp_target DROP COLUMN IF EXISTS source_question_id")
