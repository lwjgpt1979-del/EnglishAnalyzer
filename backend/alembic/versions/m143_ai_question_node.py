"""R8 Phase6-前置:练习核心 AiQuestion 挂 node(KP-First),解除 knowledge_points 删表前置

给 ai_questions 加 node_id(FK→knowledge_nodes)并把旧 knowledge_point_id 改可空:
练习生成改经 match_kp 命中 node 落 node_id(未命中留 NULL);不再经 get_or_create 建 knowledge_points。
旧 knowledge_point_id 列体保留到 Phase6 连 knowledge_points 一并 drop。

Revision ID: m143_ai_question_node
Revises: m142_user_paper_question_node
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m143_ai_question_node"
down_revision = "m142_user_paper_question_node"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_questions",
        sa.Column("node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id"), nullable=True),
    )
    op.create_index("ix_ai_questions_node_id", "ai_questions", ["node_id"])
    # 旧硬 FK 放开非空约束(生成不再必写),列体待 Phase6 drop
    op.alter_column("ai_questions", "knowledge_point_id", nullable=True)


def downgrade() -> None:
    op.alter_column("ai_questions", "knowledge_point_id", nullable=False)
    op.drop_index("ix_ai_questions_node_id", table_name="ai_questions")
    op.drop_column("ai_questions", "node_id")
