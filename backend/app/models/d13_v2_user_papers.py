"""域13: V2 学生整卷上传 (3 张表)
  user_uploaded_papers · user_paper_questions · user_paper_question_knowledge_points
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d6_ai_questions import ai_question_type_enum


class UserUploadedPaper(Base):
    __tablename__ = "user_uploaded_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    title = mapped_column(sa.String, nullable=True)
    source_image_urls = mapped_column(JSONB, nullable=False)
    image_hash = mapped_column(sa.String(32), nullable=True, index=True)  # 整套图片合并 md5(同套图重复上传去重)
    image_md5s = mapped_column(JSONB, nullable=True)  # 每张图内容 md5 列表(子集去重:新图已在某卷里→复用)
    content_hash = mapped_column(sa.String(32), nullable=True, index=True)  # 识别文本内容 md5(同卷重拍去重)
    duplicate_of = mapped_column(UUID(as_uuid=True), nullable=True)  # 判为重复卷时指向原卷(不重复解析、不列第二条)
    ocr_status = mapped_column(sa.String, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class UserPaperSection(Base):
    """整卷的「大题/板块」结构(还原原卷题型结构):单项选择 / 完形填空 / 阅读理解 / 书面表达…

    一卷多大题,大题内多题;完形/阅读的「短文+多小问」按 block_key 在题上共享 passage。
    label=原卷大题名;section_type=题型板块键(mcq/cloze/reading/…);sort_order 保原卷顺序。
    """
    __tablename__ = "user_paper_sections"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False)
    label = mapped_column(sa.String, nullable=False)          # 大题名(原卷识别 或 AI 建议)
    section_type = mapped_column(sa.String, nullable=True)    # 题型板块键
    # AI 建议的分类(原卷没识别到大题头时按题型推):前端标「建议」,学生可改;改后置 false
    is_suggested = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    # 阅读理解:是否已由学生手动加入「作业精讲·阅读理解精讲」(默认否,不自动加入)
    in_reading_intensive = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))


class UserPaperQuestion(Base):
    __tablename__ = "user_paper_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False)
    # 还原原卷结构:归属大题 + 语篇分组(完形/阅读同篇共享 passage)+ 卷面顺序
    section_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_paper_sections.id", ondelete="SET NULL"), nullable=True)
    passage = mapped_column(sa.Text, nullable=True)           # 该题所属短文/语篇(完形/阅读;独立题为空)
    block_key = mapped_column(sa.String, nullable=True)       # 同篇小问共享的分组键
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    question_no = mapped_column(sa.String, nullable=True)
    question_type = mapped_column(ai_question_type_enum, nullable=True)
    stem = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    matched_exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True)
    # R8 Phase4:组卷 KP 链改走 KP-First 的 node(match_kp 命中挂节点,未命中留 NULL 并落候选)。
    # 取代旧 user_paper_question_knowledge_points(硬 FK→knowledge_points)。
    node_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True)
    kp_key = mapped_column(sa.String(120), nullable=True)   # 归类知识点名(判语法/词汇、加入语法学习/单词用)
    # P1 阅读学情:阅读小题的题型细标(细节理解/主旨大意/推理判断/词义猜测/作者态度/指代关系/图表数字/其他)。
    # 精讲顺手写 + 存量回填 + 补跑归类;对错用现成 is_wrong。见 reading_qtype_service。
    reading_skill = mapped_column(sa.String(16), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


# R8 Phase4 已退役:题↔KP 关联改为 UserPaperQuestion.node_id(见上)。
# 表体待 Phase6 连同 knowledge_points 一并 drop,此处保留仅为迁移期兼容,业务代码不再读写。


class OcrCache(Base):
    """OCR 结果暂存(按图片内容 md5 全局缓存)。OCR/豆包 Vision 是拆卷最贵一步,
    同一张图(含不同学生上传的相同图)只识别一次,命中不重复付费。"""
    __tablename__ = "ocr_cache"

    image_md5 = mapped_column(sa.String(32), primary_key=True)
    printed_text = mapped_column(sa.Text, nullable=False, server_default="")
    handwritten_text = mapped_column(sa.Text, nullable=False, server_default="")
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class KpClassifyCache(Base):
    """题目知识点归类结果暂存(按小题内容 md5 全局缓存)。同一小题(独立题按题干、
    阅读/完形题按短文+题干)只归类一次,跨上传/跨学生复用,重叠题不重复调 LLM。"""
    __tablename__ = "kp_classify_cache"

    content_md5 = mapped_column(sa.String(32), primary_key=True)
    kp_key = mapped_column(sa.String(120), nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class PaperSplitCache(Base):
    """拆题(整卷/题型段 文字 → 结构化题目)LLM 结果暂存,按输入文本 md5 全局缓存。
    仅传统 OCR / 真题 PDF 文本层会真调 DeepSeek 拆题 LLM;豆包 Vision 直出 JSON 不经此。
    real_extract 按题型段分段调用 → 天然「按块」缓存;整卷调用则「按卷」缓存。"""
    __tablename__ = "paper_split_cache"

    input_md5 = mapped_column(sa.String(32), primary_key=True)
    raw_json = mapped_column(sa.Text, nullable=False)   # 拆题 LLM 的原始 JSON 输出(命中后复用解析)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class ReadingAnalysisCache(Base):
    """阅读理解精讲·题目层解析(题型/定位句/为何对/干扰项)LLM 结果暂存。
    按(原文+题干+选项+答案)md5 全局缓存,与用户无关;同题不二次付费(第三方付费暂存铁律)。"""
    __tablename__ = "reading_analysis_cache"

    q_md5 = mapped_column(sa.String(32), primary_key=True)
    analysis = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class ReadingPracticeCache(Base):
    """阅读理解练同类:按本篇短文生成的「理解新题」LLM 结果暂存,按(短文+题型+数量)md5 全局缓存。"""
    __tablename__ = "reading_practice_cache"

    cache_md5 = mapped_column(sa.String(32), primary_key=True)
    questions = mapped_column(JSONB, nullable=False)   # [{stem,options,answer,explanation}]
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class ReadingQuestionStudied(Base):
    """阅读理解精讲「已精讲」记录:学生看过某阅读题解析 / 练过其同类即算学过。
    作业精讲卷列表据此算 studied/未学·学习中·已学。(student, question) 唯一,幂等。"""
    __tablename__ = "reading_question_studied"

    student_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
