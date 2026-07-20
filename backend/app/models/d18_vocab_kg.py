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


class VocabWordKp(Base):
    """单词考点·词级属性 + 「已生成」标记(存在即表示 word_kp 已 LLM 生成过,不重复付费)。
    关系型考点在 VocabWordRelation;此表只放非关系属性(词根)。"""

    __tablename__ = "vocab_word_kp"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True)
    root = mapped_column(sa.String(64), nullable=True)          # 词根/词干(无则空)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class VocabWordRelation(Base):
    """单词考点·词-词/词-短语/词-文本 关系(词汇关系图):近义/反义/易混/搭配/派生/考法。
    related_word_id 命中词库时填(可点击去学);未命中只留 related_text。全关系型,无 JSONB。"""

    __tablename__ = "vocab_word_relation"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    relation = mapped_column(sa.String(16), nullable=False)    # synonym|antonym|confusion|collocation|derivation|exam_tip
    related_word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="SET NULL"), nullable=True)
    related_text = mapped_column(sa.Text, nullable=False)      # 相关词/短语/考法文本(总有)
    related_zh = mapped_column(sa.Text, nullable=True)         # 中文
    note = mapped_column(sa.Text, nullable=True)              # 辨析要点/备注
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_vocab_word_relation_word", "word_id"),
        sa.UniqueConstraint("word_id", "relation", "related_text", name="uq_vocab_word_relation"),
    )


class VocabKpMcq(Base):
    """考点扩展测试题库:按考点维度出题(每维 3 道单选),LLM 一次全生成缓存,测试时每维随机取 1。
    word_id 外键指向 vocab_word_kp(与「单词考点」强关联:有考点才有考点题);dimension 标该题测哪一维。"""

    __tablename__ = "vocab_kp_mcq"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_kp.word_id", ondelete="CASCADE"), nullable=False)
    dimension = mapped_column(sa.String(16), nullable=False)    # collocation|synonym|antonym|derivation|confusion|exam_tip
    stem = mapped_column(sa.Text, nullable=False)               # 题干
    options = mapped_column(JSONB, nullable=False)              # [str] 选项
    answer = mapped_column(sa.Text, nullable=False)            # 正确项(与 options 之一完全一致)
    explanation = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_kp_mcq_word", "word_id"),)


class VocabMcq(Base):
    """词汇测试题库(每词 3-5 道混合单选题,LLM 生成一次全局缓存,测试时随机取 1)。
    词义丰富的词出到 5 道、简单单义词 3 道;类型 w2m(词→义)/m2w(义→词)/cloze(语境填空)。"""

    __tablename__ = "vocab_mcq"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    mcq_type = mapped_column(sa.String(12), nullable=False)     # w2m|m2w|cloze
    stem = mapped_column(sa.Text, nullable=False)               # 题干(中文问法或英文挖空句)
    options = mapped_column(JSONB, nullable=False)              # [str] 4 选项
    answer = mapped_column(sa.Text, nullable=False)            # 正确项(与 options 之一完全一致)
    explanation = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_mcq_word", "word_id"),)


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
