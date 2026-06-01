"""域12: V2 真题与仿真题 (5 张表)
  exam_papers · exam_questions · exam_question_knowledge_points · simulated_questions
  · sim_practice_records
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d1_users import semester_enum
from .d6_ai_questions import ai_question_type_enum

exam_source_enum = sa.Enum("official_seed", "teacher_upload", name="exam_source")
exam_status_enum = sa.Enum("draft", "published", "retired", name="exam_status")
sim_status_enum = sa.Enum("draft", "reviewing", "published", "retired", name="sim_status")


class ExamPaper(Base):
    __tablename__ = "exam_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = mapped_column(exam_source_enum, nullable=False)
    uploader_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    class_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    region = mapped_column(sa.String, nullable=True)
    title = mapped_column(sa.String, nullable=False)
    paper_url = mapped_column(sa.String, nullable=True)
    ocr_status = mapped_column(sa.String, nullable=True)
    status = mapped_column(exam_status_enum, nullable=False, server_default=sa.text("'draft'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_papers.id"), nullable=False)
    question_no = mapped_column(sa.String, nullable=False)
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    stem = mapped_column(sa.Text, nullable=False)
    options = mapped_column(JSONB, nullable=True)
    answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class ExamQuestionKnowledgePoint(Base):
    __tablename__ = "exam_question_knowledge_points"
    exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), primary_key=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True)
    relevance = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("100"))


class SimulatedQuestion(Base):
    __tablename__ = "simulated_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False)
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    stem = mapped_column(sa.Text, nullable=False)
    options = mapped_column(JSONB, nullable=True)
    answer = mapped_column(sa.Text, nullable=False)
    explanation = mapped_column(sa.Text, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=False)
    generation_metadata = mapped_column(JSONB, nullable=True)
    status = mapped_column(sim_status_enum, nullable=False, server_default=sa.text("'draft'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class SimPracticeRecord(Base):
    """V2 仿真题逐题作答日志（练习 + 模拟考都写）。

    用途：学情按知识点聚合正确率。knowledge_point_id 冗余自 simulated_questions，
    避免聚合时 JOIN。每次作答（无论对错）写一行。
    """
    __tablename__ = "sim_practice_records"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True)
    simulated_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("simulated_questions.id"), nullable=False)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False, index=True)
    is_correct = mapped_column(sa.Boolean, nullable=False)
    user_answer = mapped_column(sa.Text, nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
