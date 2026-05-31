"""
域6: AI 题库与练习 (2 张表)
  ai_questions · practice_records
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

ai_question_type_enum = sa.Enum(
    "单选", "填空", "完型", "阅读", "写作", "判断",
    name="ai_question_type",
)
trigger_type_enum = sa.Enum(
    "module8_free", "wrong_q_followup",
    name="trigger_type",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class AiQuestion(Base):
    """AI 生成的练习题（绑定知识点，可关联课单元）。"""

    __tablename__ = "ai_questions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False
    )
    unit_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("curriculum_units.id"), nullable=True
    )
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    difficulty = mapped_column(sa.SmallInteger, nullable=False)  # 1-5
    content = mapped_column(JSONB, nullable=False)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    generated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    usage_count = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    # G20: 补充 updated_at
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class PracticeRecord(Base):
    """学生做题记录。"""

    __tablename__ = "practice_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("ai_questions.id"), nullable=False
    )
    trigger_type = mapped_column(trigger_type_enum, nullable=False)
    student_answer = mapped_column(JSONB, nullable=False)
    is_correct = mapped_column(sa.Boolean, nullable=False)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True
    )
    practiced_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    time_spent_sec = mapped_column(sa.Integer, nullable=True)
