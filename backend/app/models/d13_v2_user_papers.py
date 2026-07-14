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
    image_hash = mapped_column(sa.String(32), nullable=True, index=True)  # 图片内容 md5(同图重复上传去重)
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
