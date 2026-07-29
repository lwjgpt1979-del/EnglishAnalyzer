"""学生学习目标(student_kp_target):把「未学/薄弱」考点显式加入 → 今日计划带出「去学」。

来源:上传试卷的未学语法(source=paper_upload)等。台账里没记录的未学考点靠它进计划。
考点被掌握后自动从计划里淡出(get_active_targets 过滤已掌握)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class StudentKpTarget(Base):
    __tablename__ = "student_kp_target"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    node_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=False)
    source = mapped_column(sa.String(24), nullable=False, server_default="manual")  # paper_upload / manual
    source_paper_id = mapped_column(UUID(as_uuid=True), nullable=True)   # 来源卷(作业精讲按批次归组)
    source_question_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 来源小题(D1 按原题切点)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        # 有/无来源题分两条部分唯一(见 m202);ORM 侧用 Index 声明便于文档对齐
        sa.Index("ix_student_kp_target_student", "student_id"),
        sa.Index("ix_skt_source_q", "source_question_id"),
    )
