"""
域4: 知识体系 (7 张表)
  knowledge_points · curriculum_units · unit_knowledge_points ·
  curriculum_words · wrong_question_knowledge_points · student_kp_mastery ·
  kp_mastery_snapshots

注意: CurriculumWord.word_id → vocabulary_words (域5)，字符串 FK，SQLAlchemy 延迟解析。
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base
# semester_enum 已在域1定义，复用避免重复注册
from .d1_users import semester_enum  # noqa: F401

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

knowledge_category_enum = sa.Enum(
    "grammar", "vocabulary", "reading", "writing", "listening",
    name="knowledge_category",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String, nullable=False, unique=True)
    name = mapped_column(sa.String, nullable=False)
    category = mapped_column(knowledge_category_enum, nullable=False)
    description = mapped_column(sa.Text, nullable=True)
    # PostgreSQL TEXT[]
    applicable_grades = mapped_column(ARRAY(sa.String), nullable=False)
    applicable_textbooks = mapped_column(ARRAY(sa.String), nullable=False)
    # 自引用 FK（树形知识点结构）
    parent_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        nullable=True,
    )
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # R10.1 语法理解探针库(词级公共复用:四维题面 + 误区,LLM 生成缓存)
    grammar_probes_json = mapped_column(JSONB, nullable=True)


class CurriculumUnit(Base):
    __tablename__ = "curriculum_units"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    unit_no = mapped_column(sa.Integer, nullable=False)
    unit_title = mapped_column(sa.String, nullable=False)
    source_text = mapped_column(sa.Text, nullable=True)   # PDF 生成时的单元原文(供重生成/析短文)
    unit_pdf_url = mapped_column(sa.String, nullable=True)  # 拆出的单元独立 PDF(COS 直链)
    # 发布闸门:draft=整理中(学生不可见)/ published=已发布(学生可见)。新建默认 draft,整理好再发布。
    status = mapped_column(sa.String, nullable=False, server_default="draft")

    __table_args__ = (
        sa.UniqueConstraint(
            "textbook_version", "grade", "semester", "unit_no",
            name="uix_curriculum_units_identity",
        ),
    )


class CurriculumUnitPassage(Base):
    """单元析出的短文/范文:听力脚本 / 阅读短文(可多篇) / 写作要求与范文。

    生成时从单元原文 AI 拆出并落库,后续可逐篇关联知识点(听力→lt-*/阅读→rc-*/写作→wr-*)。
    """

    __tablename__ = "curriculum_unit_passages"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = mapped_column(sa.String(12), nullable=False)        # 听力|阅读|写作
    title = mapped_column(sa.String(200), nullable=True)
    text = mapped_column(sa.Text, nullable=False)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                               server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_cu_passage_unit", "unit_id", "kind"),)


class UnitPassageKp(Base):
    """单元短文 ↔ 知识图谱考点(复合 PK)。听力短文→lt-*/阅读→rc-*/写作→wr-*。"""

    __tablename__ = "unit_passage_kp"

    passage_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_unit_passages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    node_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                               server_default=sa.func.now())


class UnitKnowledgePoint(Base):
    """课单元与知识点多对多（复合 PK）。"""

    __tablename__ = "unit_knowledge_points"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )


class CurriculumWord(Base):
    """课单元词汇表（word_id → vocabulary_words，域5，字符串 FK，延迟解析）。"""

    __tablename__ = "curriculum_words"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id"),
        primary_key=True,
    )
    word_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("vocabulary_words.id"),  # 域5，延迟解析
        primary_key=True,
    )
    is_core = mapped_column(sa.Boolean, nullable=False)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))


class WrongQuestionKnowledgePoint(Base):
    """错题与知识点多对多（AI 诊断结果关联）。"""

    __tablename__ = "wrong_question_knowledge_points"

    wrong_question_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("wrong_questions.id"),
        primary_key=True,
    )
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id"),
        primary_key=True,
    )


class StudentKpMastery(Base):
    """每位学生对每个知识点的掌握台账（M39）。

    kp_key 为知识点名称字符串，是联合主键的一部分。
    标准教材 KP → kp_id 填写对应 UUID；教师/自定义 KP → kp_id = NULL。
    sources 记录累积写入的来源列表（去重），如 ['practice', 'paper_upload', 'assignment']。
    kp_description 为知识点简介（标准KP来自 knowledge_points.description，自定义KP可由 AI 填入）。
    """

    __tablename__ = "student_kp_mastery"

    student_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    kp_key = mapped_column(sa.Text, nullable=False, primary_key=True)
    kp_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    correct_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # 贡献来源列表，去重存储，如 ['practice', 'paper_upload', 'assignment', 'wrong_question']
    sources = mapped_column(ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'"))
    # 知识点简介：标准KP来自 knowledge_points.description，自定义KP可由 AI 填入
    kp_description = mapped_column(sa.Text, nullable=True)
    last_activity_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)


class KpMasterySnapshot(Base):
    """KP 掌握度日快照（M46 趋势图数据源）。

    每次 upsert_mastery 时写入/更新当天的快照行（按 UTC 日期去重）。
    存储当时的 correct_count / wrong_count / accuracy，用于绘制趋势折线。
    UNIQUE(student_id, kp_key, snapshot_date) 保证每天最多一行。
    """

    __tablename__ = "kp_mastery_snapshots"

    id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    student_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kp_key = mapped_column(sa.Text, nullable=False)
    snapshot_date = mapped_column(sa.Date, nullable=False)      # UTC 日期
    accuracy = mapped_column(sa.Float, nullable=False, default=0.0)
    correct_count = mapped_column(sa.Integer, nullable=False, default=0)
    wrong_count = mapped_column(sa.Integer, nullable=False, default=0)
    recorded_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint("student_id", "kp_key", "snapshot_date",
                            name="uq_kp_snapshot_student_kp_date"),
    )


class StudentGrammarMastery(Base):
    """R10.1 学生 × 语法知识点 的可解释掌握(四维 BKT)。镜像 R9 VocabularyLearning。

    recognize(识别)/ detect(纠错)/ produce(产出)各一条 BKT;transfer_ok(迁移)。
    R10.1 落 recognize/detect;produce/transfer 留 R10.2/3。
    """

    __tablename__ = "student_grammar_mastery"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                       server_default=sa.text("gen_random_uuid()"))
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kp_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    mastery_recognize = mapped_column(sa.Numeric(5, 4), nullable=True)
    mastery_detect = mapped_column(sa.Numeric(5, 4), nullable=True)
    mastery_produce = mapped_column(sa.Numeric(5, 4), nullable=True)
    transfer_ok = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    prior_source = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'default'"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    last_seen_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    last_retain_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    # R10.5 间隔复测排期
    mastered_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)         # 四维门槛首达
    next_retain_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)      # 下次复测到期
    retain_interval_days = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    retain_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.text("now()"))
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.text("now()"))

    __table_args__ = (
        sa.UniqueConstraint("student_id", "kp_id", name="uq_sgm_student_kp"),
    )


class GrammarPlacementSession(Base):
    """R10.6 语法分级测验(CAT 冷启动)会话:二分定位 + 知识空间推断 + BKT 暖启动。"""

    __tablename__ = "grammar_placement_session"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                       server_default=sa.text("gen_random_uuid()"))
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    textbook = mapped_column(sa.String, nullable=True)
    grade = mapped_column(sa.String, nullable=True)
    pool_kp_ids = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    asked = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    lo = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    hi = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    status = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'active'"))
    result_priors = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.text("now()"))
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.text("now()"))
