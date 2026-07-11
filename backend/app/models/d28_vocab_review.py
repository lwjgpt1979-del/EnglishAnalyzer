"""词库缺词审核队列(vocab_review)。

作业/课程里出现、但词库 VocabularyWord 里没有的词 → 落此队列,admin 审核后加入词库。
类比知识点候选 KpCandidate:按归一化词形去重累加 occur_count,超管审核 approve/reject。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class VocabReview(Base):
    __tablename__ = "vocab_review"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_norm = mapped_column(sa.String(80), nullable=False, unique=True)  # 归一化词形(小写去重键)
    word = mapped_column(sa.String(80), nullable=False)                    # 原词形(展示)
    source = mapped_column(sa.String(16), nullable=False, server_default="paper")  # paper / homework / course
    occur_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    status = mapped_column(sa.String(12), nullable=False, server_default="pending")  # pending/approved/rejected
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_vocab_review_status", "status"),)
