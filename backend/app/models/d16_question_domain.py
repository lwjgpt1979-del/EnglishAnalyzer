"""域16: 题分域 + 个人窄表骨架（KP-First 重构 R0.5）。

按域物理分表(设计 §4-5),结构性隔离平台与个人,杜绝个人内容越界进平台:
  - platform_question   平台题(真题/仿真),硬独立,全员共享
  - uploaded_question   非平台上传题(机构/个人),owner_scope+owner_id 隔离;**无任何指向
                        platform_question 的外键**——硬墙
  - passage             语料(篇章/音频/对话原文),分域
  - platform_question_kp / uploaded_question_kp   题↔KP 多对多(node_id → 新 knowledge_nodes)
  - student_kp          个人知识图谱投影
  - answer_log          作答事件(按月 RANGE 分区,见迁移 m83)
  - wrong_record        错题事件(指向某道题 + 定位 KP)

枚举字段一律 varchar(同 d15),取值在 service 层校验。R0.5 只建表,不灌数据;
作答/题数据的业务在 R2(平台题)/R3(错题)/R4(个人图谱)。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class PlatformQuestion(Base):
    """平台题:真题(real)/仿真(sim)。硬独立,审核发布,全员共享。"""

    __tablename__ = "platform_question"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = mapped_column(sa.String(8), nullable=False)                 # real|sim
    parent_real_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("platform_question.id"), nullable=True
    )  # sim 派生自哪道真题；real 为 null
    is_fallback = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sim_version = mapped_column(sa.SmallInteger, nullable=True)         # 仿真题按"题位(母题/短文组)"累加的版本号 v1/v2…
    deprecated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    paper_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("platform_paper.id"), nullable=True
    )  # 所属试卷(整卷上传分组);单题/仿真可为 null
    section = mapped_column(sa.String(24), nullable=True)              # 原卷大题名(听力选择/单项填空/完形填空…)
    block_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("passage.id"), nullable=True
    )  # 所属题型块(承载 passage)
    question_no = mapped_column(sa.String(16), nullable=True)
    question_type = mapped_column(sa.String(16), nullable=True)
    stem = mapped_column(sa.Text, nullable=True)
    options = mapped_column(JSONB, nullable=True)
    answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=True)          # 认知层级 1–5
    # ── 可筛选字段(从批次 meta 落列,便于按教材/学段/年级/地区/考试类型查询)──
    textbook_version = mapped_column(sa.String(24), nullable=True)
    stage = mapped_column(sa.String(8), nullable=True)                  # 小|初|高
    grade = mapped_column(sa.String(12), nullable=True)
    semester = mapped_column(sa.String(4), nullable=True)               # 上|下
    region_code = mapped_column(sa.String(12), nullable=True)           # 省/市 code
    region_name = mapped_column(sa.String(64), nullable=True)
    exam_type = mapped_column(sa.String(12), nullable=True)             # 中考|高考|普通
    meta = mapped_column(JSONB, nullable=True)                          # 其余元信息(年份等)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.Index("ix_platform_question_type_status", "type", "status"),
        sa.Index("ix_platform_question_parent", "parent_real_id"),
        sa.Index("ix_platform_question_paper", "paper_id"),
        sa.Index("ix_platform_question_book", "textbook_version", "stage", "grade"),
        sa.Index("ix_platform_question_region", "region_code"),
        sa.Index("ix_platform_question_exam", "exam_type"),
    )


class PlatformPaper(Base):
    """平台试卷:一次整卷上传 = 一份试卷,聚合其下所有真题(小题挂 paper_id)。"""

    __tablename__ = "platform_paper"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(128), nullable=False)               # 试卷名(可自动合成)
    textbook_version = mapped_column(sa.String(24), nullable=True)
    stage = mapped_column(sa.String(8), nullable=True)                 # 小|初|高
    grade = mapped_column(sa.String(12), nullable=True)
    semester = mapped_column(sa.String(4), nullable=True)              # 上|下
    region_code = mapped_column(sa.String(12), nullable=True)          # 最细到市(4位)
    region_name = mapped_column(sa.String(64), nullable=True)
    exam_type = mapped_column(sa.String(12), nullable=True)            # 中考/高考/普通
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))
    source_file_url = mapped_column(sa.String(512), nullable=True)     # 批量上传的原卷(word/pdf)COS 直链
    source_filename = mapped_column(sa.String(256), nullable=True)     # 原始文件名
    parse_status = mapped_column(sa.String(12), nullable=True)         # None/空=未解析 | parsing | parsed | failed
    year = mapped_column(sa.SmallInteger, nullable=True)               # 从试卷名提取的年份
    meta = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class UploadedQuestion(Base):
    """非平台上传题(机构/个人)。**永不进 platform_question**(物理硬墙)。"""

    __tablename__ = "uploaded_question"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_scope = mapped_column(sa.String(12), nullable=False)          # institution|student
    owner_id = mapped_column(UUID(as_uuid=True), nullable=False)
    paper_id = mapped_column(UUID(as_uuid=True), nullable=True)
    block_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("passage.id"), nullable=True)
    question_no = mapped_column(sa.String(16), nullable=True)
    question_type = mapped_column(sa.String(16), nullable=True)
    stem = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_uploaded_question_owner", "owner_scope", "owner_id"),
    )


class Passage(Base):
    """语料:篇章/听力音频/对话原文。分域。在题型块级承载,小题引用其 id。"""

    __tablename__ = "passage"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = mapped_column(sa.String(12), nullable=False)                # platform|institution|student
    owner_id = mapped_column(UUID(as_uuid=True), nullable=True)
    kind = mapped_column(sa.String(16), nullable=False)                 # reading_text|audio|dialogue
    text = mapped_column(sa.Text, nullable=True)
    audio_url = mapped_column(sa.String(512), nullable=True)
    source_ref = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_passage_scope_owner", "scope", "owner_id"),
    )


class PlatformQuestionKp(Base):
    """平台题 ↔ KP 多对多(node_id → 新 knowledge_nodes)。"""

    __tablename__ = "platform_question_kp"

    question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("platform_question.id", ondelete="CASCADE"), primary_key=True
    )
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )


class UploadedQuestionKp(Base):
    """上传题 ↔ KP 多对多。"""

    __tablename__ = "uploaded_question_kp"

    question_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("uploaded_question.id", ondelete="CASCADE"), primary_key=True
    )
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )


class StudentKp(Base):
    """个人知识图谱投影:学生 × KP 的个体状态。"""

    __tablename__ = "student_kp"

    student_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    mastery = mapped_column(sa.Numeric(5, 4), nullable=True)            # 掌握度 0–1
    practice_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # 加权掌握度计数器(m139):首答对/首答错 + 订正对/订正错;独立于 practice_count/wrong_count
    # (后者仍是总作答次数,供既有正确率/弱项)。掌握度公式见 kp_mastery_service.weighted_mastery。
    fa_correct = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))       # 首答对
    fa_wrong = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))         # 首答错
    corrected_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))  # 订正做对(每题首次)
    redo_wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0")) # 订正又做错(每次)
    last_practice_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    source_tags = mapped_column(ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'"))
    in_scope = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))


class AnswerLog(Base):
    """作答事件(按月 RANGE 分区,分区键 answered_at;PK 含分区键)。

    大表就是它,按时间分区控量。建表与默认/月分区见迁移 m83。
    """

    __tablename__ = "answer_log"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), nullable=False)
    q_scope = mapped_column(sa.String(12), nullable=False)              # platform|uploaded
    question_id = mapped_column(UUID(as_uuid=True), nullable=False)
    is_correct = mapped_column(sa.Boolean, nullable=False)
    feature = mapped_column(sa.String(24), nullable=True)
    # m119:事件行直接挂 node(platform/uploaded/ai 统一可聚合;完整性由上游保证,故不加 FK)
    node_id = mapped_column(UUID(as_uuid=True), nullable=True)
    answered_at = mapped_column(
        sa.TIMESTAMP(timezone=True), primary_key=True, nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.Index("ix_answer_log_student_time", "student_id", "answered_at"),
        sa.Index("ix_answer_log_node_time", "node_id", "answered_at"),
    )


class WrongRecord(Base):
    """错题事件:答错了某道题(指向 platform/uploaded 题)+ 定位 KP。错题不是题类型,是事件。"""

    __tablename__ = "wrong_record"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), nullable=False)
    q_scope = mapped_column(sa.String(12), nullable=False)              # platform|uploaded
    question_id = mapped_column(UUID(as_uuid=True), nullable=False)
    node_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True)
    is_original = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    # 冗余题面(统一错题中枢自洽,「我的错题」只读本表):
    stem = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    question_type = mapped_column(sa.String(24), nullable=True)
    kp_kind = mapped_column(sa.String(12), nullable=True)     # grammar|vocab
    kp_name = mapped_column(sa.String(120), nullable=True)
    source_label = mapped_column(sa.String(16), nullable=True)  # 整卷|平台|长难句|作业
    source_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 来源实体id(卷/作业),供「回到错题来源」跳转
    vocab_word_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 词汇错题定位到的目标词(词力通闭环,P3)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'open'"))  # open|mastered
    mastery_source = mapped_column(sa.String(10), nullable=True)        # review|manual|auto(N仿真)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    mastered_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    # SM-2 间隔重复(R3 承接错题复习)
    review_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # 练同类作答统计(方案B):区分待巩固/巩固中 + 纳入掌握判定
    practice_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    practice_correct = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    easiness_factor = mapped_column(sa.Numeric(4, 2), nullable=False, server_default=sa.text("2.50"))
    review_interval_days = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    next_review_at = mapped_column(sa.Date, nullable=True)
    last_review_at = mapped_column(sa.Date, nullable=True)

    __table_args__ = (
        sa.Index("ix_wrong_record_student_status", "student_id", "status"),
        sa.Index("ix_wrong_record_due", "student_id", "next_review_at"),
        sa.UniqueConstraint("student_id", "q_scope", "question_id", name="uix_wrong_record_identity"),
    )


class RealExtractJob(Base):
    """真题抽题异步任务(TK2):上传 PDF/图片 → 后台 OCR/拆题 → parsed 待校对 → 校对后批量导入。"""

    __tablename__ = "real_extract_job"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = mapped_column(sa.String(8), nullable=False)            # pdf|image
    file_id = mapped_column(sa.String(64), nullable=True)           # pdf 上传 id
    image_urls = mapped_column(JSONB, nullable=True)                # 图片 OCR 源
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'running'"))  # running|done|failed
    parsed = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))  # 抽出待校对题
    error = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (sa.Index("ix_real_extract_job_status", "status"),)
