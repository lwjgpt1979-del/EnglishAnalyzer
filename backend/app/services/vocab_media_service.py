"""词力通图背单词媒体业务（P1 / D-101）。

generate_for_word：英文描述（LLM，dev-mock 出固定文本）+ 多图 + 双音频（provider dev-mock），
写库默认 media_status='draft'，运营审核后 published。
"""
from __future__ import annotations

import random
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d5_learning import VocabularyWord
from app.models.d9_system import SystemConfig
from app.services import llm_provider, vocab_media_provider

# ── 配图提示词配置中心（system_configs，可后台配）─────────────────────────────
_IMG_KEY = "vocab_image_gen"
_IMG_TTL = 60.0
_img_cache: dict = {"data": None, "ts": 0.0}

_DEF_PRIMARY = (
    'A clear, simple illustration that obviously represents the English word "{word}" '
    '({meaning}), for children learning English vocabulary. Single clear subject, clean '
    'plain background, NO text, letters or numbers anywhere in the image.'
)
_DEF_STYLES = [
    "flat vector illustration, bright cheerful colors",
    "cute kawaii cartoon style, soft pastel colors",
    "simple watercolor illustration, gentle warm tones",
    "clean minimalist illustration with light soft shading",
    "friendly rounded 3D render, soft studio lighting",
]


def _default_img_config() -> dict:
    return {"batch_size": 20, "images_per_word": 1,
            "primary": _DEF_PRIMARY, "styles": list(_DEF_STYLES)}


def _merge_img_config(saved: dict | None) -> dict:
    cfg = _default_img_config()
    if isinstance(saved, dict):
        try:
            cfg["batch_size"] = max(1, min(int(saved.get("batch_size", cfg["batch_size"])), 200))
        except (TypeError, ValueError):
            pass
        try:
            cfg["images_per_word"] = max(1, min(int(saved.get("images_per_word", 1)), 3))
        except (TypeError, ValueError):
            pass
        if saved.get("primary"):
            cfg["primary"] = str(saved["primary"])
        if isinstance(saved.get("styles"), list):
            s = [str(x).strip() for x in saved["styles"] if str(x).strip()]
            if s:
                cfg["styles"] = s
    return cfg


async def get_image_config(db: AsyncSession) -> dict:
    now = time.time()
    if _img_cache["data"] is not None and now - _img_cache["ts"] < _IMG_TTL:
        return _img_cache["data"]
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _IMG_KEY)
    )).scalar_one_or_none()
    cfg = _merge_img_config(row.value if row is not None else None)
    _img_cache.update(data=cfg, ts=now)
    return cfg


async def set_image_config(db: AsyncSession, *, config: dict, updated_by) -> dict:
    value = _merge_img_config(config)
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _IMG_KEY)
    )).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_IMG_KEY, value=value,
                            description="词力通配图提示词配置(主要要求+随机风格+批量)",
                            updated_by=updated_by))
    else:
        row.value, row.updated_by = value, updated_by
    await db.flush()
    _img_cache["data"] = None
    return value


def _build_prompts(cfg: dict, *, word: str, meaning: str, n: int) -> list[str]:
    """主要要求(固定模板) + 次要随机风格 → n 条提示词。"""
    try:
        base = cfg["primary"].format(word=word, meaning=meaning or word)
    except Exception:  # noqa: BLE001 模板占位写错时退化
        base = f'{cfg["primary"]} word: "{word}".'
    styles = cfg.get("styles") or [""]
    picks = random.sample(styles, k=min(n, len(styles))) if len(styles) >= n else \
        [random.choice(styles) for _ in range(n)]
    return [f"{base} Style: {s}." if s else base for s in picks]


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


async def _gen_images_for(db: AsyncSession, w: VocabularyWord, cfg: dict | None = None) -> list[str]:
    """按配置(主要要求+随机风格)为单词批量构造提示词并逐条出图(转存COS)。"""
    cfg = cfg or await get_image_config(db)
    meaning = _primary_meaning(w)
    prompts = _build_prompts(cfg, word=w.word, meaning=meaning, n=int(cfg.get("images_per_word", 1)))
    urls: list[str] = []
    for p in prompts:
        u = await vocab_media_provider.t2i_to_cos(p, label=w.word)
        if u:
            urls.append(u)
    return urls


async def generate_for_word(db: AsyncSession, *, word_id: uuid.UUID) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    meaning = _primary_meaning(w)
    en = await _gen_en_description(w.word, meaning)
    w.en_description = en
    imgs = await _gen_images_for(db, w)
    if imgs:
        w.image_urls = imgs
    wa = vocab_media_provider.generate_tts(w.word)
    ea = vocab_media_provider.generate_tts(en)
    if wa:
        w.word_audio_url = wa      # mock 返回空 → 不覆盖（卡片发音走火山 TTS 兜底）
    if ea:
        w.en_desc_audio_url = ea
    w.media_status = "draft"
    await db.flush()
    return w


# ── 批量生成（后台触发，进程内进度）────────────────────────────────────────────
_batch_state: dict = {"running": False, "total": 0, "done": 0, "ok": 0, "failed": 0}


def batch_status() -> dict:
    return dict(_batch_state)


async def _run_batch(word_ids: list, cfg: dict) -> None:
    from app.core.database import _async_session_factory
    _batch_state.update(running=True, total=len(word_ids), done=0, ok=0, failed=0)
    try:
        for wid in word_ids:
            async with _async_session_factory() as db:
                try:
                    w = (await db.execute(
                        select(VocabularyWord).where(VocabularyWord.id == wid)
                    )).scalar_one_or_none()
                    if w is not None:
                        imgs = await _gen_images_for(db, w, cfg)
                        if imgs:
                            w.image_urls = imgs
                            w.media_status = "draft"
                            await db.commit()
                            _batch_state["ok"] += 1
                        else:
                            _batch_state["failed"] += 1
                    else:
                        _batch_state["failed"] += 1
                except Exception:  # noqa: BLE001
                    _batch_state["failed"] += 1
            _batch_state["done"] += 1
    finally:
        _batch_state["running"] = False


async def start_batch_image_gen(db: AsyncSession) -> dict:
    """对「未配图」的单词，按配置 batch_size 取一批，后台批量生成配图。"""
    import asyncio
    if _batch_state["running"]:
        return {"started": False, "reason": "已有批量任务进行中", **batch_status()}
    cfg = await get_image_config(db)
    n = int(cfg.get("batch_size", 20))
    rows = (await db.execute(
        select(VocabularyWord.id).where(
            (VocabularyWord.image_urls.is_(None))
            | (func.jsonb_array_length(VocabularyWord.image_urls) == 0)
        ).limit(n)
    )).all()
    ids = [r[0] for r in rows]
    if not ids:
        return {"started": False, "reason": "没有待配图的单词", "total": 0}
    asyncio.create_task(_run_batch(ids, cfg))
    return {"started": True, "total": len(ids)}


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
