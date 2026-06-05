"""域11: V2 教材深度内容 (1 张表)
  knowledge_point_contents
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base

dimension_enum = sa.Enum(
    "listening", "vocabulary", "grammar", "reading", "translation", "writing",
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
