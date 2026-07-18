"""学生个人语法节点(student_grammar_node):个人语法树里「没匹配上知识图谱」的那部分。

个人语法树 = 组合视图,读取时拼:
  ① 当前教材进度内、从知识图谱取的语法节点(共享只读骨架,不复制);
  ② 各渠道学过且匹配上图谱的节点(掌握度走 StudentKp);
  ③ 没匹配上图谱的知识 —— 就存这张表,挂在骨架对应位置(anchor_code)。
个人节点天然算「未学」(无 StudentKp 台账),直到被匹配进图谱(回填 ref_node_id)。
不做「后台择优收编回公共图谱」——个人的归个人。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class StudentGrammarNode(Base):
    __tablename__ = "student_grammar_node"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    name = mapped_column(sa.String(120), nullable=False)
    name_norm = mapped_column(sa.String(120), nullable=False)              # 归一化去重键
    ref_node_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True)  # 匹配上图谱则回填
    anchor_code = mapped_column(sa.String(32), nullable=True)              # 挂靠的图谱骨架 code(定位在树里的位置)
    source_paper_id = mapped_column(UUID(as_uuid=True), nullable=True)     # 来源上传作业(作业精讲·语法按卷归组用)
    source = mapped_column(sa.String(24), nullable=False, server_default="upload_paper")  # upload_paper / homework
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    # 自建语法没有图谱 node、无 BKT 四维掌握;改用「练一练痕迹」记已学 + 最近一轮成绩(作业精讲·语法列表反馈用)
    studied_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)   # 练过/看过讲解即置 → studied
    last_correct = mapped_column(sa.Integer, nullable=True)                  # 最近一轮练习答对数
    last_total = mapped_column(sa.Integer, nullable=True)                    # 最近一轮练习总题数

    __table_args__ = (
        sa.UniqueConstraint("student_id", "name_norm", name="uix_student_grammar_node"),
        sa.Index("ix_student_grammar_node_student", "student_id"),
    )
