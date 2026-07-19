"""域18: 词汇接入 KP-First(R5)。

词条(vocabulary_words)↔ KP/真题/错题 三种边 + 通用词库(平台域,超管维护)。
词条本体仍是 d5.VocabularyWord(R5 扩了 type/source/frequency/star);本域只建关联与词库。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class VocabWordFamily(Base):
    """词族缓存(全局共享,G 构词法):词 → 词根 + 同族词。LLM 生成一次即缓存,查看即生成。"""

    __tablename__ = "vocab_word_family"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True)
    root = mapped_column(sa.String(64), nullable=True)          # 词根/词干(无明显则空)
    members = mapped_column(JSONB, nullable=False)              # [{word, pos, meaning}] 同族词(不含原词)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class VocabNode(Base):
    """词 ↔ 知识节点(R5)。一词多 KP、一 KP 多词。"""

    __tablename__ = "vocab_node"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True
    )
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    source = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'textbook'"))  # textbook|exam|manual
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_node_node", "node_id"),)


class VocabQuestion(Base):
    """词 ↔ 题(平台/上传)。词在题里出现 → 建边(背词溯源/真题频率增强)。"""

    __tablename__ = "vocab_question"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True
    )
    q_scope = mapped_column(sa.String(12), primary_key=True)        # platform|uploaded
    question_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    source = mapped_column(sa.String(16), nullable=True)            # stem|option|explanation
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class VocabWrong(Base):
    """词 ↔ 错题事件(wrong_record)。错题里的生词 → 建边。"""

    __tablename__ = "vocab_wrong"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True
    )
    wrong_record_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_record.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class VocabList(Base):
    """通用词库(平台域,超管维护):中考词表/高考3500/CET…"""

    __tablename__ = "vocab_list"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(120), nullable=False, unique=True)
    exam_level = mapped_column(sa.String(32), nullable=True)        # primary|junior|senior|cet4|cet6
    source_type = mapped_column(sa.String(24), nullable=True)       # official_syllabus|exam_frequency|textbook_frequency
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))  # draft|published|archived
    maintained_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )


class VocabListItem(Base):
    """通用词库条目:词库 ↔ 词条(带库内属性 rank/frequency/star)。"""

    __tablename__ = "vocab_list_item"

    list_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_list.id", ondelete="CASCADE"), primary_key=True
    )
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True
    )
    rank = mapped_column(sa.Integer, nullable=True)                 # 频率排名(1 最高频)
    frequency = mapped_column(sa.Integer, nullable=True)
    star = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("0"))
    verified = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    # R真题词频:frequency 复用为「中考真题卷频次」、star 为高/中/低频档(3/2/1/0);
    # added_from_exam=true 表示考纲原本无、因真题出现被补录(区分原生考纲词)。
    added_from_exam = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    __table_args__ = (sa.Index("ix_vocab_list_item_word", "word_id"),)
