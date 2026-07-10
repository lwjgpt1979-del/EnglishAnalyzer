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
    # R8 Phase4:组卷 KP 链改走 KP-First 的 node(match_kp 命中挂节点,未命中留 NULL 并落候选)。
    # 取代旧 user_paper_question_knowledge_points(硬 FK→knowledge_points)。
    node_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


# R8 Phase4 已退役:题↔KP 关联改为 UserPaperQuestion.node_id(见上)。
# 表体待 Phase6 连同 knowledge_points 一并 drop,此处保留仅为迁移期兼容,业务代码不再读写。
