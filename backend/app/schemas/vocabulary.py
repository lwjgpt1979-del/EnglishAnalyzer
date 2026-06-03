"""词力通词汇学习 schemas（P1 / D-100）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class WordCardOut(BaseModel):
    """词卡（学习展示用）。"""
    word_id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] | dict  # vocabulary_words.definitions（JSONB 原样）
    examples: list | dict | None = None
    difficulty: int
    level: str = Field(..., description="new/learning/review/mastered")
    is_new: bool = Field(..., description="今日新词 True / 复习词 False")


class DailyTaskOut(BaseModel):
    """每日学习任务。"""
    new_words: list[WordCardOut]
    review_words: list[WordCardOut]
    new_count: int
    review_count: int
    new_limit: int = Field(..., description="当前会员档位每日新词上限")


class VocabAnswerIn(BaseModel):
    word_id: uuid.UUID
    correct: bool
    hesitant: bool = Field(False, description="记得但不确定：熟练度不升级、间隔不延长")


class VocabAnswerResult(BaseModel):
    word_id: uuid.UUID
    level: str
    repetitions: int
    interval_days: int
    next_review_at: str = Field(..., description="ISO 时间")


# ─── 图背单词媒体（运营 admin，P1 / D-101）────────────────────────────────────

class AdminVocabMediaItem(BaseModel):
    word_id: uuid.UUID
    word: str
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None
    media_status: str


class AdminVocabMediaListOut(BaseModel):
    total: int
    items: list[AdminVocabMediaItem]


class VocabMediaReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")


class VocabMediaUpdateRequest(BaseModel):
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None
