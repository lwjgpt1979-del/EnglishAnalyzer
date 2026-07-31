"""学生单元语法细目闯关(A1/Q+)过关记录 + 缺句示范句全局缓存。"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class StudentGrammarFacetPass(Base):
    """学生在某单元某图谱节点下通过某一细目(一句三练微测)。"""

    __tablename__ = "student_grammar_facet_pass"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), nullable=False)
    unit_id = mapped_column(UUID(as_uuid=True), nullable=False)
    node_id = mapped_column(UUID(as_uuid=True), nullable=False)
    facet_name = mapped_column(sa.String(80), nullable=False)
    passed_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "unit_id", "node_id", "facet_name",
            name="uq_student_grammar_facet_pass"),
        sa.Index("ix_sgfp_student_unit_node", "student_id", "unit_id", "node_id"),
    )


class GrammarFacetDemoCache(Base):
    """细目缺可用教材句时 LLM 示范句全局缓存(按 point|facet md5)。"""

    __tablename__ = "grammar_facet_demo_cache"

    input_md5 = mapped_column(sa.String(32), primary_key=True)
    point_name = mapped_column(sa.String(120), nullable=False)
    facet_name = mapped_column(sa.String(80), nullable=False)
    sentences = mapped_column(JSONB, nullable=False)
    zh_hints = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
