"""域22: 单元结构化解析(「重新生成短文」第一步产物)。

LLM 解析单元原文 → 结构化板块:
  - 语法部分:每个**挂靠点**(粗语法点)可带双层细目 facets + 原文例句;
    挂知识图谱只认挂靠点,细目仅展示/教案用。
  - 听力部分:每个**听力考点**下挂一组句子。
  - 作文部分:**作文要求**(教材指令)+ **正文**(书本原文)。

语法点/听力考点 第一步只是 LLM 抽出的**名字**(point_name),node_id 留空;
第二步「关联知识图谱」再用 match_kp 把它们挂到 knowledge_nodes(填 node_id)。
"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base


class UnitSection(Base):
    """单元结构化板块。kind ∈ grammar(语法点)/ listening(听力考点)/ writing(作文)。"""

    __tablename__ = "curriculum_unit_section"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = mapped_column(sa.String(12), nullable=False)            # grammar|listening|writing
    point_name = mapped_column(sa.String(200), nullable=True)      # LLM 抽的 语法点名/听力考点名
    # 第二步「关联知识图谱」填:语法点/听力考点 → knowledge_nodes
    node_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    node_code = mapped_column(sa.String(64), nullable=True)        # 关联后的考点编码(冗余,便于展示)
    requirement = mapped_column(sa.Text, nullable=True)            # 听力/作文 的教材指令「要求」
    body_text = mapped_column(sa.Text, nullable=True)             # 作文「正文(书本原文)」
    extract_source = mapped_column(sa.String(16), nullable=True)  # pdf|paste — 关联时内容来源
    # 语法双层细目:[{name, sentences:[原文句...]}];挂靠仍用本行 point_name/node_id
    facets = mapped_column(JSONB, nullable=True)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_unit_section_unit", "unit_id", "kind"),)


class UnitSectionSentence(Base):
    """板块下挂的句子(从单元原文抽),带 0–100 难度分(syntactic_complexity)。"""

    __tablename__ = "curriculum_unit_section_sentence"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_unit_section.id", ondelete="CASCADE"),
        nullable=False,
    )
    text = mapped_column(sa.Text, nullable=False)                  # 句子原文
    difficulty = mapped_column(sa.Integer, nullable=True)          # 0–100 难易分
    syntax_points = mapped_column(JSONB, nullable=True)            # 命中的句法点(detect_syntax_points)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))

    __table_args__ = (sa.Index("ix_unit_section_sentence_section", "section_id"),)


class UnitStructuredParseCache(Base):
    """单元结构化 LLM 解析缓存(按原文 md5,同输入不二次付费)。"""

    __tablename__ = "unit_structured_parse_cache"

    content_md5 = mapped_column(sa.String(32), primary_key=True)
    result = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
