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
    # —— R5 词汇并入(KP-First):词条类型/来源/频率/星级 ——
    type = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'word'"))  # word|phrase
    source = mapped_column(sa.String(16), nullable=True)        # seed|ai|textbook|exam|import
    frequency = mapped_column(sa.Integer, nullable=True)        # 词频排名(小=高频)
    star = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("0"))  # 考频星级 0-5
    # —— 图背单词媒体（P1 词力通深化 / D-101；dev-mock 占位，真生成留 config 接缝）——
    image_urls = mapped_column(JSONB, nullable=True)
    en_description = mapped_column(sa.Text, nullable=True)
    word_audio_url = mapped_column(sa.String, nullable=True)
    en_desc_audio_url = mapped_column(sa.String, nullable=True)
    media_status = mapped_column(sa.String, nullable=False, server_default=sa.text("'draft'"))
    # R9.1 理解探针库(词级公共复用):{distractors, misconceptions, cloze_fallback, sense}
    probes_json = mapped_column(JSONB, nullable=True)


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
    # R9 词汇可输入性理解:接收/产出双维掌握度(BKT,0-1)+ 同词新语境迁移
    mastery_recep = mapped_column(sa.Numeric(5, 4), nullable=True)
    mastery_prod = mapped_column(sa.Numeric(5, 4), nullable=True)
    transfer_ok = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
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
    source = mapped_column(sa.String(20), nullable=False)  # paper/wrong_question/manual/pick/photo
    # R9.6 优先学:0=普通候选,>0=学生主动优先学(数值越大越先);拍照/挑选加入即置>0
    priority = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("0"))
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
    wrong_carry_threshold = mapped_column(sa.Integer, nullable=False, server_default=sa.text("2"))
    # R5 收尾:通用词库 opt-in(默认关;开后背词加选通用词库,可指定某词库)
    include_general_vocab = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    general_vocab_list_id = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )


class VocabPronLog(Base):
    """词力通跟读发音评测日志（用于学情报表/趋势/薄弱词）。"""

    __tablename__ = "vocab_pron_logs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True)
    reference_text = mapped_column(sa.String, nullable=False)
    word_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), nullable=True)
    overall = mapped_column(sa.SmallInteger, nullable=False)
    accuracy = mapped_column(sa.SmallInteger, nullable=True)
    fluency = mapped_column(sa.SmallInteger, nullable=True)
    completion = mapped_column(sa.SmallInteger, nullable=True)
    weak = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class EssayPrompt(Base):
    """作文题库（应试训练）：体裁 + 提纲要点 + 人称/时态/词数。"""

    __tablename__ = "essay_prompts"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage = mapped_column(sa.String(16), nullable=False)        # junior / senior / primary
    genre = mapped_column(sa.String(24), nullable=False)        # 书信/通知/记叙/议论/看图/读后续写
    title = mapped_column(sa.String, nullable=False)
    scenario = mapped_column(sa.Text, nullable=False)           # 情景/提纲原文
    required_points = mapped_column(JSONB, nullable=False)      # 必答要点 [str]
    person = mapped_column(sa.String(16), nullable=True)
    tense = mapped_column(sa.String(24), nullable=True)
    word_min = mapped_column(sa.SmallInteger, nullable=True)
    word_max = mapped_column(sa.SmallInteger, nullable=True)
    source = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'admin'"))
    parent_prompt_id = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class EssayErrorLog(Base):
    """作文写作错因本：高频错误归类沉淀。"""

    __tablename__ = "essay_error_log"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True)
    essay_id = mapped_column(UUID(as_uuid=True), nullable=True)
    type = mapped_column(sa.String(24), nullable=False)         # 时态/主谓/中式表达/拼写/搭配/...
    original = mapped_column(sa.Text, nullable=True)
    suggestion = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


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


class ListeningWrongQuestion(Base):
    """听力错题归集（§6.4）：精听答错的题目，供错题库重练。"""

    __tablename__ = "listening_wrong_questions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    exercise_id = mapped_column(sa.String, nullable=False)
    exercise_title = mapped_column(sa.String, nullable=True)
    question_index = mapped_column(sa.SmallInteger, nullable=False)
    prompt = mapped_column(sa.Text, nullable=False)
    options = mapped_column(JSONB, nullable=True)
    correct_index = mapped_column(sa.SmallInteger, nullable=False)
    chosen_index = mapped_column(sa.SmallInteger, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    last_wrong_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "student_id", "exercise_id", "question_index",
            name="uix_listening_wrong",
        ),
    )


class ListeningShadowWeak(Base):
    """听力跟读薄弱句库（§6.4）：取最高分，best_score<60 为薄弱、优先复现。"""

    __tablename__ = "listening_shadow_weak"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    sentence = mapped_column(sa.Text, nullable=False)
    best_score = mapped_column(sa.SmallInteger, nullable=False)
    attempts = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    last_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("student_id", "sentence", name="uix_listening_shadow_weak"),
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
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
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
