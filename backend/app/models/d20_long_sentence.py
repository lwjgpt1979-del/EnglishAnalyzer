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
    difficulty = mapped_column(sa.Integer, nullable=True)                 # 句法复杂度难度分 0–100(spaCy 依存:从句数/树深/MDD/词数)
    # —— 定位元数据(平台库必带;按来源不同维度有效)——
    textbook_version = mapped_column(sa.String(64), nullable=True)        # 教材版本
    stage = mapped_column(sa.String(8), nullable=True)                    # 学段:小|初|高(中考/高考真题主定位维度)
    grade = mapped_column(sa.String(32), nullable=True)                   # 年级
    semester = mapped_column(sa.String(8), nullable=True)                 # 学期:上|下
    unit_id = mapped_column(UUID(as_uuid=True), nullable=True)           # 教材来源:定位到课程单元(curriculum_units.id)
    exam_type = mapped_column(sa.String(12), nullable=True)               # 真题来源:普通|中考|高考
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


class StudentLongSentence(Base):
    """学生个人长难句(独立表):学生上传作业时抽取,只对本人可见。

    与平台 long_sentence 彻底分开(学生量大、重效率);无教材定位维度,直接发布。
    """

    __tablename__ = "student_long_sentence"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = mapped_column(UUID(as_uuid=True), nullable=False)           # 学生
    source_question_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 来源:上传题(uploaded_question.id)
    source_paper_id = mapped_column(UUID(as_uuid=True), nullable=True)     # 来源卷(作业精讲按批次归组)
    text = mapped_column(sa.Text, nullable=False)
    analysis_json = mapped_column(JSONB, nullable=True)
    difficulty = mapped_column(sa.Integer, nullable=True)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'published'"))  # 默认本人可见
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_student_long_sentence_owner", "owner_id", "status"),
        sa.Index("ix_student_long_sentence_srcq", "source_question_id"),
    )


class StudentLsState(Base):
    """学生长难句自适应水平 θ(0–100,与 difficulty 同尺);随做题/反馈持续校准。"""

    __tablename__ = "student_ls_state"

    user_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    theta = mapped_column(sa.Numeric(5, 2), nullable=False)               # 当前水平估计
    seen_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())


class StudentLsReview(Base):
    """间隔重现:学生标记「难」的长难句进复习盒,到期再推;盒越高间隔越长,满盒毕业。"""

    __tablename__ = "student_ls_review"

    user_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    ls_id = mapped_column(UUID(as_uuid=True), primary_key=True)            # 平台/个人长难句 id
    is_student = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))  # 来源:个人库?
    box = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))             # Leitner 盒 1..N
    due_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)    # 到期可重推时间
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (sa.Index("ix_student_ls_review_due", "user_id", "due_at"),)


class LongSentenceFavorite(Base):
    """学生 ↔ 长难句 收藏。"""

    __tablename__ = "long_sentence_favorite"

    user_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    long_sentence_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("long_sentence.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_ls_favorite_user", "user_id"),)


class SentenceAnalysisCache(Base):
    """长难句解析结果暂存(按句子文本 md5 缓存 LLM 解析,命中不再重复付费调用)。

    第三方付费调用暂存规则的落地:analyze_sentence 结果与学生无关(同句同解析),
    全局按 text_hash 缓存;analyze_sentence_cached 先查后算。
    """
    __tablename__ = "sentence_analysis_cache"

    text_hash = mapped_column(sa.String(32), primary_key=True)   # 归一化句子的 md5
    text = mapped_column(sa.Text, nullable=False)
    analysis_json = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class StudentGrammarQuizStat(Base):
    """长难句语法提问式选择的正确率统计(以往至今累计,按学生×语法点)。

    gp_key:语法点稳定键(匹配到语法节点则用 node_id,否则 name:归一名)。供学习页
    「考查完给所有语法点统计正确率」。
    """
    __tablename__ = "student_grammar_quiz_stat"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    gp_key = mapped_column(sa.String(64), nullable=False)
    node_id = mapped_column(UUID(as_uuid=True), nullable=True)
    label = mapped_column(sa.String(120), nullable=False)
    correct = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    total = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                               server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("student_id", "gp_key", name="uq_grammar_quiz_stat_student_gp"),
    )
