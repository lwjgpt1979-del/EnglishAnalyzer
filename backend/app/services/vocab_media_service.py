"""词力通图背单词媒体业务（P1 / D-101）。

generate_for_word：英文描述（LLM，dev-mock 出固定文本）+ 多图 + 双音频（provider dev-mock），
写库默认 media_status='draft'，运营审核后 published。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d5_learning import VocabularyWord
from app.services import llm_provider, vocab_media_provider


def _primary_meaning(w: VocabularyWord) -> str:
    d = w.definitions
    if isinstance(d, list) and d:
        return str(d[0].get("meaning", ""))
    return ""


async def _gen_en_description(word: str, meaning: str) -> str:
    """英文可理解性描述：dev-mock 出固定模板；真 LLM 走 chat_completion。"""
    if llm_provider.is_llm_dev_mode():
        return (
            f"'{word}' means {meaning}. Use it in simple English: "
            f"This is a clear, learner-friendly explanation of the word '{word}'."
        )
    resp = await llm_provider.chat_completion(
        system_prompt=(
            "You are an English teacher. Explain the word for a young learner "
            "using simple English (CEFR A2). 2-3 short sentences, no Chinese."
        ),
        user_prompt=f"Word: {word}\nChinese meaning: {meaning}",
        max_tokens=200,
    )
    return (resp.choices[0].message.content or "").strip()


async def generate_for_word(db: AsyncSession, *, word_id: uuid.UUID) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    meaning = _primary_meaning(w)
    en = await _gen_en_description(w.word, meaning)
    w.en_description = en
    w.image_urls = await vocab_media_provider.generate_images(w.word, n=settings.image_count_per_word)
    wa = vocab_media_provider.generate_tts(w.word)
    ea = vocab_media_provider.generate_tts(en)
    if wa:
        w.word_audio_url = wa      # mock 返回空 → 不覆盖（卡片发音走火山 TTS 兜底）
    if ea:
        w.en_desc_audio_url = ea
    w.media_status = "draft"
    await db.flush()
    return w


async def review_word_media(
    db: AsyncSession, *, word_id: uuid.UUID, approve: bool,
) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    w.media_status = "published" if approve else "retired"
    await db.flush()
    return w


async def update_word_media(
    db: AsyncSession,
    *,
    word_id: uuid.UUID,
    image_urls: list[str] | None = None,
    en_description: str | None = None,
    word_audio_url: str | None = None,
    en_desc_audio_url: str | None = None,
) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    if image_urls is not None:
        w.image_urls = image_urls
    if en_description is not None:
        w.en_description = en_description
    if word_audio_url is not None:
        w.word_audio_url = word_audio_url
    if en_desc_audio_url is not None:
        w.en_desc_audio_url = en_desc_audio_url
    await db.flush()
    return w


async def list_words_for_media_review(
    db: AsyncSession, *, media_status: str = "draft", skip: int = 0, limit: int = 20,
) -> tuple[list[VocabularyWord], int]:
    base = select(VocabularyWord).where(VocabularyWord.media_status == media_status)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabularyWord.word).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total
