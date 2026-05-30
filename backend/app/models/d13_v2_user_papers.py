"""域13: V2 学生整卷上传 (3 张表)
  user_uploaded_papers · user_paper_questions · user_paper_question_knowledge_points
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d6_ai_questions import ai_question_type_enum


class UserUploadedPaper(Base):
    __tablename__ = "user_uploaded_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    title = mapped_column(sa.String, nullable=True)
    source_image_urls = mapped_column(JSONB, nullable=False)
    ocr_status = mapped_column(sa.String, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class UserPaperQuestion(Base):
    __tablename__ = "user_paper_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False)
    question_no = mapped_column(sa.String, nullable=True)
    question_type = mapped_column(ai_question_type_enum, nullable=True)
    stem = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    matched_exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class UserPaperQuestionKnowledgePoint(Base):
    __tablename__ = "user_paper_question_knowledge_points"
    user_paper_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_paper_questions.id"), primary_key=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True)
