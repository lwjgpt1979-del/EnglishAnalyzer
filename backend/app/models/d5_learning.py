"""
域5: 学习功能 (5 张表)
  vocabulary_words · vocabulary_learning · essays ·
  listening_records · study_checkins
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

vocab_level_enum = sa.Enum(
    "new", "learning", "review", "mastered",
    name="vocab_level",
)
essay_status_enum = sa.Enum(
    "draft", "processing", "completed",
    name="essay_status",
)
listening_status_enum = sa.Enum(
    "processing", "completed", "failed",
    name="listening_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class VocabularyWord(Base):
    """单词词典（全局共享，不绑定学生）。"""

    __tablename__ = "vocabulary_words"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word = mapped_column(sa.String, nullable=False)
    phonetic = mapped_column(sa.String, nullable=True)
    definitions = mapped_column(JSONB, nullable=False)
    examples = mapped_column(JSONB, nullable=True)   # 例句 [{en, zh}]
    phrases = mapped_column(JSONB, nullable=True)    # 短语 [{en, zh}]
    difficulty = mapped_column(sa.SmallInteger, nullable=False)  # 1-5
    # —— 图背单词媒体（P1 词力通深化 / D-101；dev-mock 占位，真生成留 config 接缝）——
    image_urls = mapped_column(JSONB, nullable=True)
    en_description = mapped_column(sa.Text, nullable=True)
    word_audio_url = mapped_column(sa.String, nullable=True)
    en_desc_audio_url = mapped_column(sa.String, nullable=True)
    media_status = mapped_column(sa.String, nullable=False, server_default=sa.text("'draft'"))


class VocabularyLearning(Base):
    """
    学生单词学习记录（SM-2 算法状态）。
    G14: 补充 created_at。
    UNIQUE (student_id, word_id)。
    """

    __tablename__ = "vocabulary_learning"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), nullable=False
    )
    interval_days = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    repetitions = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    easiness_factor = mapped_column(
        sa.Numeric(4, 2), nullable=False, server_default=sa.text("2.5")
    )
    next_review_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    last_reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    level = mapped_column(vocab_level_enum, nullable=False)
    # —— 错词本联动（P1 词力通深化 / D-103）——
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # G14: 补充 created_at
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "word_id",
            name="uix_vocabulary_learning_student_word",
        ),
    )


class StudentVocabCandidate(Base):
    """学生词力通"其他来源"候选词（P2，M50）。

    从上传试卷 / 错题文本里抽出的、命中词典的生词，作为该生当前学期其他来源
    的待学候选。选新词时优先级介于"当前学期教材词"(P1) 与"过往购买学期词"(P3) 之间。
    UNIQUE (student_id, word_id) 保证不重复。
    """

    __tablename__ = "student_vocab_candidates"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    word_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), nullable=False
    )
    source = mapped_column(sa.String(20), nullable=False)  # 'paper' / 'wrong_question'
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "word_id",
            name="uix_student_vocab_candidate_student_word",
        ),
    )


class StudentVocabSetting(Base):
    """学生词力通学习设置（每生一份）。

    不再按会员档位限量：每组学多少词 / 每组学多少遍 由用户自定。
    UNIQUE(student_id)。
    """

    __tablename__ = "student_vocab_settings"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True
    )
    words_per_group = mapped_column(sa.Integer, nullable=False, server_default=sa.text("5"))
    reps_per_group = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )


class Essay(Base):
    """学生作文润色记录（可多轮）。"""

    __tablename__ = "essays"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    wrong_question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True
    )
    original_text = mapped_column(sa.Text, nullable=False)
    polished_text = mapped_column(sa.Text, nullable=True)
    dimensions = mapped_column(JSONB, nullable=True)
    round_count = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("1")
    )
    status = mapped_column(essay_status_enum, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class ListeningRecord(Base):
    """听力口语练习记录。"""

    __tablename__ = "listening_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    audio_url = mapped_column(sa.String, nullable=False)
    reference_url = mapped_column(sa.String, nullable=False)
    status = mapped_column(listening_status_enum, nullable=False)
    score = mapped_column(sa.Numeric(5, 2), nullable=True)
    feedback = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class StudyCheckin(Base):
    """每日学习打卡（每生每天唯一）。"""

    __tablename__ = "study_checkins"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    checkin_date = mapped_column(sa.Date, nullable=False)
    new_words_count = mapped_column(sa.Integer, nullable=False)
    review_done = mapped_column(sa.Boolean, nullable=False)
    streak_days = mapped_column(sa.Integer, nullable=False)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "checkin_date",
            name="uix_study_checkins_student_date",
        ),
    )


class SpeakingSession(Base):
    """口语对话练习记录（每完成一次结束评价写一条）。供口语维度学情 + 打卡。"""

    __tablename__ = "speaking_sessions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True
    )
    scenario_key = mapped_column(sa.String, nullable=False)
    source = mapped_column(sa.String, nullable=True)          # 词力通 / 错题薄弱点 / 学期内容 / 通用
    score = mapped_column(sa.SmallInteger, nullable=True)     # 本次综合评分 0-100
    turns = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    used_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    missed_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
