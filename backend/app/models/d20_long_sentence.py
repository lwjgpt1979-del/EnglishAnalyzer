"""域20: 长难句解析(KP-First 句法轴应用入口)。

长难句**有源**(来自真题/教材/上传,记 source 指针),挂句法 knowledge_nodes(多对多),
解析存 analysis_json(主干/分层/译文/难点/句法点)。复用 R0–R7 骨架,不新建体系。
枚举字段用 varchar,取值 service 层校验。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class LongSentence(Base):
    """长难句条目(挂来源 + 解析)。"""

    __tablename__ = "long_sentence"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'platform'"))  # platform|student
    owner_id = mapped_column(UUID(as_uuid=True), nullable=True)            # student scope 时为学生
    # 来源指针(有源):平台题/上传题/语料
    source_kind = mapped_column(sa.String(16), nullable=False)            # platform_real|textbook|uploaded
    source_q_scope = mapped_column(sa.String(12), nullable=True)          # platform|uploaded(指向题)
    source_question_id = mapped_column(UUID(as_uuid=True), nullable=True)
    source_passage_id = mapped_column(UUID(as_uuid=True), nullable=True)
    text = mapped_column(sa.Text, nullable=False)                         # 句子原文
    analysis_json = mapped_column(JSONB, nullable=True)                   # 主干/分层/译文/难点/句法点
    audio_url = mapped_column(sa.Text, nullable=True)                     # 听原句:TTS 合成后存 COS 的直链(首次回填,再次直接播)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))  # draft|published|retired
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.Index("ix_long_sentence_source", "source_kind", "source_question_id"),
        sa.Index("ix_long_sentence_scope_status", "scope", "status"),
    )


class LongSentenceNode(Base):
    """长难句 ↔ 句法知识节点(多对多)。"""

    __tablename__ = "long_sentence_node"

    long_sentence_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("long_sentence.id", ondelete="CASCADE"), primary_key=True
    )
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )

    __table_args__ = (sa.Index("ix_long_sentence_node_node", "node_id"),)


class LongSentenceFavorite(Base):
    """学生 ↔ 长难句 收藏。"""

    __tablename__ = "long_sentence_favorite"

    user_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    long_sentence_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("long_sentence.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_ls_favorite_user", "user_id"),)
