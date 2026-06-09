"""
域3: 错题与 AI 诊断 (3 张表)
  wrong_questions · ocr_tasks · ai_analyses
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

question_type_enum = sa.Enum(
    "单选", "完型", "阅读", "作文", "其他", "填空", "判断",
    name="question_type",
)
ocr_status_enum = sa.Enum(
    "pending", "processing", "completed", "failed",
    name="ocr_status",
)
ocr_provider_enum = sa.Enum(
    "aliyun_print", "baidu_print", "tencent_handwrite", "google_handwrite",
    name="ocr_provider",
)
llm_provider_enum = sa.Enum(
    "deepseek", "claude",
    name="llm_provider",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    source_image_url = mapped_column(sa.String, nullable=False)
    question_text = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    question_type = mapped_column(question_type_enum, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=True)
    tags = mapped_column(JSONB, nullable=True)
    is_mastered = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    mastered_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    ocr_status = mapped_column(ocr_status_enum, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    # ── SM-2 间隔重复字段（M36）────────────────────────────────────────────────
    review_count = mapped_column(sa.Integer, nullable=False, server_default="0")
    easiness_factor = mapped_column(
        sa.Numeric(precision=4, scale=2), nullable=False, server_default="2.50"
    )
    review_interval_days = mapped_column(sa.Integer, nullable=False, server_default="1")
    next_review_at = mapped_column(sa.Date, nullable=True)
    last_review_at = mapped_column(sa.Date, nullable=True)


class OcrTask(Base):
    """OCR 任务（4层流水线状态跟踪）。"""

    __tablename__ = "ocr_tasks"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    status = mapped_column(ocr_status_enum, nullable=False)
    provider = mapped_column(ocr_provider_enum, nullable=True)
    raw_result = mapped_column(JSONB, nullable=True)
    error_message = mapped_column(sa.Text, nullable=True)
    retry_count = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    completed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)


class AiAnalysis(Base):
    """AI 诊断结果（每次分析生成一条，不可更新）。"""

    __tablename__ = "ai_analyses"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    llm_provider = mapped_column(llm_provider_enum, nullable=False)
    error_types = mapped_column(JSONB, nullable=False)
    knowledge_points = mapped_column(JSONB, nullable=False)
    diagnosis = mapped_column(sa.Text, nullable=False)
    suggestions = mapped_column(sa.Text, nullable=False)
    confidence_score = mapped_column(sa.Numeric(4, 3), nullable=True)
    tokens_used = mapped_column(sa.Integer, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class TeacherComment(Base):
    """教师对错题的批注。"""

    __tablename__ = "teacher_comments"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False
    )
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    comment_text = mapped_column(sa.Text, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
