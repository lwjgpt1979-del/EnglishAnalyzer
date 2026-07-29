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


class VocabWordSense(Base):
    """单词/词组义项(1B 词义消歧):一个词的各义项(but:①转折·但是·conj ②除…外·prep)。
    考点(vocab_word_relation)与考点测试(vocab_kp_mcq)按 sense_id 归属义项;错题按上下文命中义项。"""

    __tablename__ = "vocab_word_sense"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    gloss_zh = mapped_column(sa.String(120), nullable=False)   # 中文义(义项标签)
    pos = mapped_column(sa.String(16), nullable=True)          # 该义项词性
    sort = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_word_sense_word", "word_id"),)


class VocabWordKp(Base):
    """单词考点·词级属性 + 「已生成」标记(存在即表示 word_kp 已 LLM 生成过,不重复付费)。
    关系型考点在 VocabWordRelation;此表只放非关系属性(词根)。"""

    __tablename__ = "vocab_word_kp"

    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True)
    root = mapped_column(sa.String(64), nullable=True)          # 词根/词干(无则空)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)  # AI 自审校时间(P5;空=未审→低峰 cron 扫)
    # 二期 AI 预隐:已对近义/易混跑过预隐则置时(空=待扫;失败不置以便重试)
    prehide_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class VocabWordRelation(Base):
    """单词/词组考点·动态维度关系图(受控可扩维度清单,按词性/特点动态):
    relation = 维度键(dim_key,见 word_kp_service._DIM_REGISTRY:时态/可数性/近义/搭配/考法…);
    relational 维的项命中词库填 related_word_id(可点去学),文本维只留 related_text。全关系型,无 JSONB。"""

    __tablename__ = "vocab_word_relation"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    sense_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_sense.id", ondelete="SET NULL"), nullable=True)  # 归属义项(1B)
    relation = mapped_column(sa.String(32), nullable=False)    # 维度键 dim_key(动态,取自受控清单)
    dim_label = mapped_column(sa.String(32), nullable=True)    # 维度中文名(写入时的快照;读取回退 registry)
    sort = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("0"))  # 维度展示顺序(registry 序)
    source = mapped_column(sa.String(8), nullable=False, server_default=sa.text("'llm'"))  # 来源:llm | morph(形态学·确定性→高置信)
    related_word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="SET NULL"), nullable=True)
    related_text = mapped_column(sa.Text, nullable=False)      # 相关词/词形/短语/文本内容(总有)
    related_zh = mapped_column(sa.Text, nullable=True)         # 中文
    note = mapped_column(sa.Text, nullable=True)              # 辨析要点/备注
    report_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))  # 学生报错数(P6;≥阈值→复核/AI修正)
    # 方案1·自动上架+举报下架:hidden_at 非空 = 对学生隐藏(行保留,防 ensure 同 text 再插入)
    hidden_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    hidden_by = mapped_column(UUID(as_uuid=True), nullable=True)   # 运营 admin user id
    hide_note = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_vocab_word_relation_word", "word_id"),
        sa.UniqueConstraint("word_id", "relation", "related_text", name="uq_vocab_word_relation"),
    )


class VocabKpRelationReport(Base):
    """考点有凭证举报(每生每条关系一行):原因标签 + 说明/建议正确项。加权进 report_count。"""

    __tablename__ = "vocab_kp_relation_report"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relation_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_relation.id", ondelete="CASCADE"), nullable=False)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reason = mapped_column(sa.String(32), nullable=False)  # meaning_mismatch|out_of_syllabus|confuse_wrong|collocation_fake|other
    detail = mapped_column(sa.Text, nullable=True)
    suggested = mapped_column(sa.Text, nullable=True)      # 我认为正确的词/用法
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("relation_id", "student_id", name="uq_vocab_kp_rel_report_student"),
        sa.Index("ix_vocab_kp_rel_report_rel", "relation_id"),
    )


class StudentWrongRelation(Base):
    """错题关系网(每个学生私有):节点 = 错题选项里的词/词组(a/b_word_id 指向 vocabulary_words);
    边 = 同一道错题的多个选项两两之间的关系。全局考点是共享的,但「谁和谁在这道错题里放一起」是私有的。
    source:global(全局考点已有该关系)/ llm(同题共现经 LLM 判定,会回写全局)/ cooccur(仅共现、无语义关系)。
    a_word_id/b_word_id 按 id 归一(a<b)防同边反向重复。"""

    __tablename__ = "student_wrong_relation"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    a_word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    b_word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    relation = mapped_column(sa.String(16), nullable=False)   # synonym|antonym|confusion|ambiguity|related|cooccur
    source = mapped_column(sa.String(8), nullable=False)      # global|llm|cooccur
    wrong_record_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_record.id", ondelete="CASCADE"), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_student_wrong_relation_student", "student_id"),
        sa.UniqueConstraint("student_id", "a_word_id", "b_word_id", "relation",
                            name="uq_student_wrong_relation"),
    )


class StudentWrongWord(Base):
    """错题关系网(以词为中心,每学生私有):某词/词组在某道错题里扮演的角色。
    role=answer(主关系:该词是正确答案,'考的就是它')/ distractor(次关系:该词只是干扰项)。
    支持"从任一词拉出它的全部错题,区分主/次"。"""

    __tablename__ = "student_wrong_word"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    wrong_record_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_record.id", ondelete="CASCADE"), nullable=False)
    sense_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_sense.id", ondelete="SET NULL"), nullable=True)  # 该错题命中的义项(S2 填)
    role = mapped_column(sa.String(10), nullable=False)   # answer(主) | distractor(次)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_student_wrong_word_sw", "student_id", "word_id"),
        sa.Index("ix_student_wrong_word_rec", "wrong_record_id"),
        sa.UniqueConstraint("student_id", "word_id", "wrong_record_id", name="uq_student_wrong_word"),
    )


class VocabKpMcq(Base):
    """考点扩展测试题库:按考点维度出题(每维 3 道单选),LLM 一次全生成缓存,测试时每维随机取 1。
    word_id 外键指向 vocab_word_kp(与「单词考点」强关联:有考点才有考点题);dimension 标该题测哪一维。"""

    __tablename__ = "vocab_kp_mcq"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_kp.word_id", ondelete="CASCADE"), nullable=False)
    sense_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_word_sense.id", ondelete="SET NULL"), nullable=True)  # 归属义项(1B)
    dimension = mapped_column(sa.String(32), nullable=False)    # 动态维度键 dim_key(见 word_kp_service._DIM_REGISTRY)
    stem = mapped_column(sa.Text, nullable=False)               # 题干
    options = mapped_column(JSONB, nullable=False)              # [str] 选项
    answer = mapped_column(sa.Text, nullable=False)            # 正确项(与 options 之一完全一致)
    explanation = mapped_column(sa.Text, nullable=True)
    # 学生「换一题」= 报错标记:被换/报错次数(>0 出题时优先避开,后台按此复核 AI 出错题)
    report_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
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


class VocabWordKpReview(Base):
    """考点 AI 自审校记录(P5):每次审校存 before/after 快照(删/改了哪些文本维考点),供后台追溯。"""

    __tablename__ = "vocab_word_kp_review"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), nullable=False)
    before = mapped_column(JSONB, nullable=True)   # [{id, dim, text, zh, note}] 审前
    after = mapped_column(JSONB, nullable=True)    # {deleted:[...], fixed:[...]} 审后动作
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_word_kp_review_word", "word_id"),)


class VocabKpMcqRevision(Base):
    """考点题修改记录:每次 AI 自动修正/人工编辑存一份 before/after 快照(后台可看修改历史)。"""

    __tablename__ = "vocab_kp_mcq_revision"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mcq_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocab_kp_mcq.id", ondelete="CASCADE"), nullable=False)
    before = mapped_column(JSONB, nullable=True)   # {stem, options, answer, explanation, report_count}
    after = mapped_column(JSONB, nullable=True)
    trigger = mapped_column(sa.String(8), nullable=False)   # auto(跨阈值自动) | manual(后台点)
    by_admin_id = mapped_column(UUID(as_uuid=True), nullable=True)
    reason = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_kp_mcq_revision_mcq", "mcq_id"),)


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
