"""R8 Phase4:老师/上传组卷题挂 node(KP-First),取代 user_paper_question_knowledge_points 旧硬 FK

给 user_paper_questions 加 node_id(FK→knowledge_nodes),题↔KP 关联收敛到 node。
旧 user_paper_question_knowledge_points 表体保留到 Phase6 连 knowledge_points 一并 drop。

Revision ID: m142_user_paper_question_node
Revises: m141_sensitive_approval
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m142_user_paper_question_node"
down_revision = "m141_sensitive_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_paper_questions",
        sa.Column("node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id"), nullable=True),
    )
    op.create_index(
        "ix_user_paper_questions_node_id", "user_paper_questions", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_user_paper_questions_node_id", table_name="user_paper_questions")
    op.drop_column("user_paper_questions", "node_id")
