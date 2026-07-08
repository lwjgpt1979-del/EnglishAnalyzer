"""考点讲解(kp_lecture)——按考点类型的「教学环节」结构化讲解。

取代旧的 node_resource 六维(听/词/语法/阅读/翻译/写作)错配设计:讲解不是「学科技能」,
而是「教学环节」,且环节随考点类型(由节点编码前缀 cf/jf/rc/lt/wr 推出)自适应。
一考点一套讲解、一环节一行(node_id + section_key 唯一),支持逐段 AI 生成 / 人工确认 / 发布。
模板(各类型的 section 集与标题)见 app/services/kp_lecture_service.py。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class KpLecture(Base):
    __tablename__ = "kp_lecture"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_key = mapped_column(sa.String(32), nullable=False)   # concept/rule/examples/...(随类型)
    content_md = mapped_column(sa.Text, nullable=True)           # 该环节正文(Markdown)
    media_url = mapped_column(sa.String, nullable=True)          # 可选:听力例题音频 / 配图
    # 发布闸门:draft=整理中(学生不可见)/ published=已发布(学生可见)
    status = mapped_column(sa.String(16), nullable=False, server_default="draft")
    source = mapped_column(sa.String(16), nullable=False, server_default="manual")  # ai / manual
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint("node_id", "section_key", name="uix_kp_lecture_identity"),
        sa.Index("ix_kp_lecture_node", "node_id"),
    )
