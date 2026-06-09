"""
域4: 知识体系 (6 张表)
  knowledge_points · curriculum_units · unit_knowledge_points ·
  curriculum_words · wrong_question_knowledge_points · student_kp_mastery

注意: CurriculumWord.word_id → vocabulary_words (域5)，字符串 FK，SQLAlchemy 延迟解析。
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import mapped_column

from .base import Base
# semester_enum 已在域1定义，复用避免重复注册
from .d1_users import semester_enum  # noqa: F401

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

knowledge_category_enum = sa.Enum(
    "grammar", "vocabulary", "reading", "writing", "listening",
    name="knowledge_category",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String, nullable=False, unique=True)
    name = mapped_column(sa.String, nullable=False)
    category = mapped_column(knowledge_category_enum, nullable=False)
    description = mapped_column(sa.Text, nullable=True)
    # PostgreSQL TEXT[]
    applicable_grades = mapped_column(ARRAY(sa.String), nullable=False)
    applicable_textbooks = mapped_column(ARRAY(sa.String), nullable=False)
    # 自引用 FK（树形知识点结构）
    parent_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        nullable=True,
    )
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))


class CurriculumUnit(Base):
    __tablename__ = "curriculum_units"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    unit_no = mapped_column(sa.Integer, nullable=False)
    unit_title = mapped_column(sa.String, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "textbook_version", "grade", "semester", "unit_no",
            name="uix_curriculum_units_identity",
        ),
    )


class UnitKnowledgePoint(Base):
    """课单元与知识点多对多（复合 PK）。"""

    __tablename__ = "unit_knowledge_points"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )


class CurriculumWord(Base):
    """课单元词汇表（word_id → vocabulary_words，域5，字符串 FK，延迟解析）。"""

    __tablename__ = "curriculum_words"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    word_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("vocabulary_words.id"),  # 域5，延迟解析
        primary_key=True,
    )
    is_core = mapped_column(sa.Boolean, nullable=False)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))


class WrongQuestionKnowledgePoint(Base):
    """错题与知识点多对多（AI 诊断结果关联）。"""

    __tablename__ = "wrong_question_knowledge_points"

    wrong_question_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("wrong_questions.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )


class StudentKpMastery(Base):
    """每位学生对每个知识点的掌握台账（M39）。

    kp_key 为知识点名称字符串，是联合主键的一部分。
    标准教材 KP → kp_id 填写对应 UUID；教师/自定义 KP → kp_id = NULL。
    """

    __tablename__ = "student_kp_mastery"

    student_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    kp_key = mapped_column(sa.Text, nullable=False, primary_key=True)
    kp_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    correct_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    last_activity_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
