"""域12: V2 真题与仿真题 (6 张表)
  exam_papers · exam_questions · exam_question_knowledge_points · simulated_questions
  · sim_practice_records · sim_exam_sessions
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d1_users import semester_enum
from .d6_ai_questions import ai_question_type_enum
from .d11_v2_curriculum import dimension_enum

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
    dimension = mapped_column(dimension_enum, nullable=True)
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


class SimExamSession(Base):
    """V2 模拟考一次性批量提交的成绩快照（成绩历史）。

    每次 submit_exam_attempts 落一行；逐题明细仍在 sim_practice_records。
    """
    __tablename__ = "sim_exam_sessions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True)
    total = mapped_column(sa.Integer, nullable=False)
    correct_count = mapped_column(sa.Integer, nullable=False)
    accuracy = mapped_column(sa.Float, nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


self_exam_status_enum = sa.Enum("answering", "done", name="self_exam_status")


class SelfExam(Base):
    """ProMax 学生自助出卷（功能模块 5C，M51）。

    一次自助生成的整卷：按学生薄弱点组卷、限时作答、一次性批改。
    错题由 submit_exam_attempts 统一落 wrong_questions；本表存配额/历史/限时/状态。
    """

    __tablename__ = "self_exams"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True
    )
    status = mapped_column(
        self_exam_status_enum, nullable=False, server_default=sa.text("'answering'")
    )
    question_ids = mapped_column(JSONB, nullable=False)   # [simulated_question id 字符串]
    snapshot = mapped_column(JSONB, nullable=False)       # 题目展示快照（不含答案）
    weak_kps = mapped_column(JSONB, nullable=True)        # 组卷依据的薄弱知识点名
    time_limit_sec = mapped_column(sa.Integer, nullable=False)
    total = mapped_column(sa.Integer, nullable=True)
    correct_count = mapped_column(sa.Integer, nullable=True)
    accuracy = mapped_column(sa.Float, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    submitted_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
