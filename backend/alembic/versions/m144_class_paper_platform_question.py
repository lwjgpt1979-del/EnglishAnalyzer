"""R8 Phase6a-2:老师组卷题源 simulated_questions → platform_question

class_paper_questions.sim_question_id(硬 FK→simulated_questions)改为
platform_question_id(FK→platform_question)。sim 与 platform 主键不同源、无法逐行重映射,
存量组卷题(dev 测试数据)清空重组。

Revision ID: m144_cpq_platform_question
Revises: m143_ai_question_node
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m144_cpq_platform_question"
down_revision = "m143_ai_question_node"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 存量组卷题挂的是 sim id,platform 无对应 → 清空(dev/未上线,班级卷重组即可)
    op.execute("DELETE FROM class_paper_questions")
    op.drop_constraint("uq_cpq_paper_question", "class_paper_questions", type_="unique")
    op.drop_column("class_paper_questions", "sim_question_id")
    op.add_column(
        "class_paper_questions",
        sa.Column("platform_question_id", UUID(as_uuid=True),
                  sa.ForeignKey("platform_question.id"), nullable=False),
    )
    op.create_unique_constraint(
        "uq_cpq_paper_question", "class_paper_questions",
        ["class_paper_id", "platform_question_id"])


def downgrade() -> None:
    op.execute("DELETE FROM class_paper_questions")
    op.drop_constraint("uq_cpq_paper_question", "class_paper_questions", type_="unique")
    op.drop_column("class_paper_questions", "platform_question_id")
    op.add_column(
        "class_paper_questions",
        sa.Column("sim_question_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulated_questions.id"), nullable=False),
    )
    op.create_unique_constraint(
        "uq_cpq_paper_question", "class_paper_questions",
        ["class_paper_id", "sim_question_id"])
