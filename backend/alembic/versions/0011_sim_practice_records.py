"""create sim_practice_records (V2 学情按 KP 聚合正确率)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-01

V2 仿真题逐题作答日志：练习/模拟考每次作答（无论对错）写一行，
用于学情按知识点聚合正确率。knowledge_point_id 冗余自 simulated_questions。
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_practice_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("simulated_question_id", UUID(as_uuid=True), sa.ForeignKey("simulated_questions.id"), nullable=False),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sim_practice_records_student_id", "sim_practice_records", ["student_id"])
    op.create_index("ix_sim_practice_records_knowledge_point_id", "sim_practice_records", ["knowledge_point_id"])


def downgrade() -> None:
    op.drop_index("ix_sim_practice_records_knowledge_point_id", table_name="sim_practice_records")
    op.drop_index("ix_sim_practice_records_student_id", table_name="sim_practice_records")
    op.drop_table("sim_practice_records")
