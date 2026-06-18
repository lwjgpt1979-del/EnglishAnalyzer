"""域11: V2 教材深度内容 (1 张表)
  knowledge_point_contents
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base

# content_dimension 被两处共用：
#   - knowledge_point_contents.dimension：教学内容，用 6 维
#     （listening/vocabulary/grammar/reading/translation/writing，不含 dictation）
#   - simulated_questions.dimension：仿真题生成，仍用 dictation（听写题）等
# 故枚举为两者并集共 7 值；dictation 仅供仿真题，教学内容不产出该维度。
dimension_enum = sa.Enum(
    "listening", "dictation", "grammar", "writing",
    "vocabulary", "reading", "translation",
    name="content_dimension",
)
content_status_enum = sa.Enum(
    "draft", "reviewing", "published", "retired",
    name="content_status",
)
generated_by_enum = sa.Enum(
    "ai_full", "ai_with_human_review",
    name="content_generated_by",
)


class KnowledgePointContent(Base):
    """每个知识点 × 6 维度（听/词汇/语法/阅读/翻译/写作）的 AI 解读内容。"""
    __tablename__ = "knowledge_point_contents"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False
    )
    dimension = mapped_column(dimension_enum, nullable=False)
    content_md = mapped_column(sa.Text, nullable=False)
    audio_url = mapped_column(sa.String, nullable=True)
    example_json = mapped_column(JSONB, nullable=True)
    status = mapped_column(content_status_enum, nullable=False, server_default=sa.text("'draft'"))
    generated_by = mapped_column(generated_by_enum, nullable=False)
    reviewed_by = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("knowledge_point_id", "dimension", name="uix_kp_dimension"),
    )


class PendingKpContent(Base):
    """生成内容暂存(KP-First):KP 未命中 knowledge_node 时,讲解按 (kp_name_norm, dimension)
    暂存于此;候选 approve/merge 出 node 后物化为 node_resource(lecture)并删除本行。
    用归一化 KP 名作键(非候选 id):persist_unit 早于候选创建,以 name_norm 解耦时序。"""

    __tablename__ = "pending_kp_content"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kp_name_norm = mapped_column(sa.String, nullable=False)
    dimension = mapped_column(sa.String(16), nullable=False)
    content_md = mapped_column(sa.Text, nullable=False)
    source_unit_id = mapped_column(UUID(as_uuid=True), nullable=True)
    generated_by = mapped_column(sa.String(24), nullable=False, server_default=sa.text("'ai_full'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False,
                              server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("kp_name_norm", "dimension", name="uix_pending_kp_dim"),
        sa.Index("ix_pending_kp_content_norm", "kp_name_norm"),
    )
