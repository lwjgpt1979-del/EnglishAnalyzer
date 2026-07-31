"""单元长难句·理解向:从粘贴原文抽尽/无则合成;不挂知识图谱。"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class UnitUnderstandLs(Base):
    """某单元理解向长难句清单(原文抽取或 AI 合成)。"""

    __tablename__ = "unit_understand_ls"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id = mapped_column(UUID(as_uuid=True), nullable=False)
    text = mapped_column(sa.Text, nullable=False)
    translation = mapped_column(sa.Text, nullable=True)
    why = mapped_column(sa.Text, nullable=True)
    src = mapped_column(sa.String(12), nullable=False)  # extract | synth
    difficulty = mapped_column(sa.Integer, nullable=True)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    course_text_md5 = mapped_column(sa.String(32), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.Index("ix_unit_understand_ls_unit", "unit_id", "sort_order"),
    )


class UnitLsUnderstandCache(Base):
    """抽尽/合成结果全局缓存(按原文 md5 + 年级 + 语法范围)。"""

    __tablename__ = "unit_ls_understand_cache"

    input_md5 = mapped_column(sa.String(32), primary_key=True)
    unit_id = mapped_column(UUID(as_uuid=True), nullable=True)
    grade = mapped_column(sa.String(32), nullable=True)
    result = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
