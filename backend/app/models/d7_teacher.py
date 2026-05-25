"""
域7: 老师端 (4 张表)
  classes · class_students · assignments · assignment_submissions
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

assignment_status_enum = sa.Enum(
    "draft", "published", "closed",
    name="assignment_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class Class(Base):
    __tablename__ = "classes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    name = mapped_column(sa.String, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class ClassStudent(Base):
    """班级-学生多对多（复合 PK）。"""

    __tablename__ = "class_students"

    class_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("classes.id"), primary_key=True
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    joined_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)


class Assignment(Base):
    """作业（可不绑定班级，teacher 直接发布给个别学生时 class_id 为 null）。"""

    __tablename__ = "assignments"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    class_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True
    )
    title = mapped_column(sa.String, nullable=False)
    questions = mapped_column(JSONB, nullable=True)
    due_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    status = mapped_column(assignment_status_enum, nullable=False)
    # G21: status→published 时写入此字段，便于统计发布延迟
    published_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class AssignmentSubmission(Base):
    """学生作业提交（每生每作业唯一）。"""

    __tablename__ = "assignment_submissions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assignments.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    answers = mapped_column(JSONB, nullable=False)
    score = mapped_column(sa.Numeric(5, 2), nullable=True)
    submitted_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "assignment_id", "student_id",
            name="uix_assignment_submissions_unique",
        ),
    )
