"""R8 Phase6c:退役旧 KP 轴——drop knowledge_points 及其 8 张关联/仿真旧表 + ai_questions.knowledge_point_id 列

KP-First 收敛收官:知识点只留 knowledge_nodes 一套主键。以下旧表全部无 app 代码读写者(经 Phase4-6a2
逐步架空),按 FK 依赖顺序(子表先、主表后)drop:
  sim_practice_records → sim_exam_sessions → simulated_questions →
  exam_question_knowledge_points → knowledge_point_contents → unit_knowledge_points →
  user_paper_question_knowledge_points → wrong_question_knowledge_points →
  (ai_questions.knowledge_point_id 列)→ knowledge_points
注:student_grammar_mastery.kp_id 早已 re-base 到 knowledge_nodes(fk_sgm_kp_node),不受影响。

Revision ID: m145_drop_legacy_kp_tables
Revises: m144_cpq_platform_question
"""
from alembic import op

revision = "m145_drop_legacy_kp_tables"
down_revision = "m144_cpq_platform_question"
branch_labels = None
depends_on = None

_TABLES_IN_DROP_ORDER = [
    "sim_practice_records",
    "sim_exam_sessions",
    "simulated_questions",
    "exam_question_knowledge_points",
    "knowledge_point_contents",
    "unit_knowledge_points",
    "user_paper_question_knowledge_points",
    "wrong_question_knowledge_points",
]


def upgrade() -> None:
    for t in _TABLES_IN_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    # 练习核心不再挂旧 KP(已改 node_id)
    op.execute("ALTER TABLE ai_questions DROP COLUMN IF EXISTS knowledge_point_id")
    # 最后 drop 主表(自引用 parent_id 随表一并删)
    op.execute("DROP TABLE IF EXISTS knowledge_points CASCADE")


def downgrade() -> None:
    # 退役表不支持回滚重建(数据与 FK 结构已随 KP-First 收敛废弃)。
    raise NotImplementedError("R8 Phase6c drop of legacy KP tables is irreversible")
