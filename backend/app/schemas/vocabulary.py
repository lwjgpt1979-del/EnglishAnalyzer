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
    phrases: list | dict | None = None
    difficulty: int
    level: str = Field(..., description="new/learning/review/mastered")
    is_new: bool = Field(..., description="今日新词 True / 复习词 False")
    # —— 图背单词媒体（仅 media_status='published' 时填充，D-101）——
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None


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


# ─── 错词本（P1 / D-103）──────────────────────────────────────────────────────

class WrongWordItem(BaseModel):
    word_id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] | dict
    wrong_count: int
    level: str
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None


class WrongWordListOut(BaseModel):
    total: int
    items: list[WrongWordItem]


# ─── 打卡激励（P1 / D-104）────────────────────────────────────────────────────

class CheckinResult(BaseModel):
    completed: bool                  # 今日任务是否达标（打卡是否发放）
    checkin_date: str | None = None  # 未达标时为 None
    streak_days: int = 0
    new_words_count: int = 0
    review_done: bool = False
    # 缺口（未完成时引导）
    review_due: int = 0
    new_learned_today: int = 0
    new_target: int = 0


class CheckinStatusOut(BaseModel):
    checked_in_today: bool
    current_streak: int
    longest_streak: int
    today_new_words: int
    today_review_done: bool


# ─── 补签 + 热力图 + 徽章（P1 / D-107）────────────────────────────────────────

class CheckinBadge(BaseModel):
    level: str
    name: str
    threshold: int
    unlocked: bool


class StudentCalendarOut(BaseModel):
    year: int
    month: int
    days: list[dict]
    checked_count: int
    current_streak: int
    longest_streak: int
    badges: list[CheckinBadge]


class MakeUpIn(BaseModel):
    date: str


class MakeUpResult(BaseModel):
    date: str
    current_streak: int
    longest_streak: int


# ── 跟读发音评分（听力跟读模块·嵌入词力通例句）────────────────────────────
class ShadowScoreIn(BaseModel):
    reference_text: str = Field(..., min_length=1, description="跟读的参照单词/句子文本")
    audio: str = Field("", description="录音 base64（空则走 dev-mock）")
    audio_format: str = Field("mp3", description="音频格式：mp3/wav/pcm")


class ShadowWordScore(BaseModel):
    word: str
    score: int


class ShadowScoreResult(BaseModel):
    overall: int
    level: str                       # excellent/good/fair/poor
    words: list[ShadowWordScore]
    tip: str
    accuracy: int | None = None      # 准确度（SOE）
    fluency: int | None = None       # 流利度（SOE）
    completion: int | None = None    # 完整度（SOE）
