"""R10 第2步:answer_log 加 node_id —— 给「真实作答」直接挂 node,补对题真值分母。

此前 answer_log 只能经 platform/uploaded_question_kp 连 node,而 AI 练习题(ai_questions)
无映射表 → 刷题对题进不了校准分母。直接在事件行上落 node_id,所有题源(platform/uploaded/ai)
统一可按 node 聚合,去掉脆弱的 question_kp join。

answer_log 按月 RANGE 分区:ADD COLUMN / CREATE INDEX 在分区父表上自动传播到各分区。
node 完整性由上游(match_kp/record_wrong)保证,大事件表不加 FK 控开销。

Revision ID: m119_answer_log_node
Revises: m118_grammar_on_nodes
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "m119_answer_log_node"
down_revision = "m118_grammar_on_nodes"
branch_labels = None
depends_on = None


def _cols(t):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(t)}


def upgrade():
    if "node_id" not in _cols("answer_log"):
        op.add_column("answer_log", sa.Column("node_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_answer_log_node_time ON answer_log (node_id, answered_at)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_answer_log_node_time")
    if "node_id" in _cols("answer_log"):
        op.drop_column("answer_log", "node_id")
