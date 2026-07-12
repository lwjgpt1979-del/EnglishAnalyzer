"""词力通图背单词媒体业务（P1 / D-101）。

generate_for_word：英文描述（LLM，dev-mock 出固定文本）+ 多图 + 双音频（provider dev-mock），
写库默认 media_status='draft'，运营审核后 published。
"""
from __future__ import annotations

import logging
import random
import time
import uuid

logger = logging.getLogger(__name__)

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d5_learning import VocabularyWord
from app.models.d9_system import SystemConfig
from app.services import llm_provider, tts_service, vocab_media_provider


async def _tts_cos(text: str) -> str:
    """火山 TTS → COS 缓存直链；失败/COS-dev 返回空串（前端再用 TTS 兜底）。"""
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return (await tts_service.get_or_create_audio_url(text)) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("[词力通TTS] %s 失败: %s", text[:20], e)
        return ""

# ── 配图提示词配置中心（system_configs，可后台配）─────────────────────────────
_IMG_KEY = "vocab_image_gen"
_IMG_TTL = 60.0
_img_cache: dict = {"data": None, "ts": 0.0}

_DEF_PRIMARY = (
    'A clear, simple illustration that visually conveys the MEANING of the English word/phrase '
    '"{word}" — {meaning}. Depict a concrete scene, object or action that unambiguously expresses '
    'this meaning; for feelings or abstract words show a character whose facial expression, posture '
    'and the surrounding situation clearly convey it, together with the object causing it. '
    'One clear focal subject, clean plain background. Do NOT draw a random generic child. '
    'Absolutely NO text, letters, numbers or words anywhere in the image.'
)
# 旧默认(诱导画小孩、词义表达差):存量配置里若仍是这句,自动升级为 _DEF_PRIMARY(不误伤自定义)
_OLD_PRIMARY = (
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
    return {"batch_size": 20, "images_per_word": 1, "use_ai_prompt": True,
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
        if "use_ai_prompt" in saved:
            cfg["use_ai_prompt"] = bool(saved["use_ai_prompt"])
        # 保留自定义 primary;但「旧默认」自动升级为新默认(同步成新版,不误伤自定义)
        sp = str(saved.get("primary") or "").strip()
        if sp and sp != _OLD_PRIMARY.strip():
            cfg["primary"] = sp
        if isinstance(saved.get("styles"), list):
            s = [str(x).strip() for x in saved["styles"] if str(x).strip()]
            if s:
                cfg["styles"] = s
    return cfg


async def _ai_visual_brief(word: str, meaning: str, pos: str) -> str:
    """用 LLM 把词(尤其抽象词/虚词/短语)转成一句"可画的具体视觉场景",提升图片可理解性。
    这是配图准确性的核心:场景越具体(动作/表情/对象/空间关系),T2I 出图越贴合词义。空/过短则重试一次。"""
    if llm_provider.is_llm_dev_mode():
        return ""   # dev-mock:不增强,走主模板
    system = (
        "You are a visual designer for a children's English vocabulary app. For the given word/phrase, "
        "design ONE vivid, concrete, unambiguous scene for a text-to-image model, so a child who sees the "
        "picture instantly grasps its MEANING.\n"
        "- Concrete noun: show that exact object as the clear focal subject.\n"
        "- Verb / action: show a character actively performing it with obvious body language.\n"
        "- Feeling / abstract word: show a character whose facial expression, posture and the surrounding "
        "situation unmistakably convey the feeling, TOGETHER WITH the object or cause of it.\n"
        "- Preposition / phrase: depict the exact spatial or situational relationship it describes.\n"
        "Rules: describe ONLY what is visible (subject, action, key objects, expression, spatial relation). "
        "Make it specific to THIS meaning — NEVER a generic child just standing or smiling. "
        "No text/letters/words in the image. No style adjectives, no explanation. Output ONE English sentence."
    )
    up = f"Word/phrase: {word}\nPart of speech: {pos}\nMeaning (Chinese): {meaning}"
    for _ in range(2):
        try:
            # 走非推理 fast 档:主模型是推理模型,max_tokens 被推理吃光→空返回(brief 生不出的根因)
            resp = await llm_provider.chat_completion(
                system_prompt=system, user_prompt=up, max_tokens=256,
                model=llm_provider.fast_model(), feature="vocab_image_brief")
            brief = (resp.choices[0].message.content or "").strip().replace("\n", " ")
            if len(brief) >= 12:      # 太短/空视为无效 → 重试一次
                return brief
        except Exception as e:  # noqa: BLE001
            logger.warning("[配图AI提示词] %s 失败: %s", word, e)
    return ""


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


def _build_prompts(cfg: dict, *, word: str, meaning: str, n: int, brief: str = "") -> list[str]:
    """(AI视觉场景 brief +) 主要要求(固定模板) + 次要随机风格 → n 条提示词。"""
    try:
        base = cfg["primary"].format(word=word, meaning=meaning or word)
    except Exception:  # noqa: BLE001 模板占位写错时退化
        base = f'{cfg["primary"]} word: "{word}".'
    if brief:
        base = f"{brief} {base}"   # AI 生成的可画场景放最前，主要要求作约束
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


def _pos_of(w: VocabularyWord) -> str:
    d = w.definitions
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return str(d[0].get("pos", ""))
    return ""


async def _ai_example_phrase(word: str, meaning: str, pos: str, brief: str) -> dict:
    """生成 例句(先贴合图片意思) + 短语。返回 {example:{en,zh}, phrase:{en,zh}}。"""
    if llm_provider.is_llm_dev_mode():
        return {"example": {"en": f"This is a {word}.", "zh": f"这是{meaning}。"},
                "phrase": {"en": word, "zh": meaning}}
    import json as _json
    scene = f" The example sentence should match this picture: {brief}." if brief else ""
    try:
        resp = await llm_provider.chat_completion(
            system_prompt=(
                "You are an English vocabulary helper for young Chinese learners. For the given word/"
                "phrase, output compact JSON with keys: example (an object {en, zh}: ONE simple CEFR-A2 "
                "example sentence using the word, plus its Chinese translation) and phrase (an object "
                "{en, zh}: ONE very common short collocation/phrase with the word, plus Chinese). "
                "Keep English simple and natural." + scene
            ),
            user_prompt=f"Word/phrase: {word}\nPart of speech: {pos}\nMeaning (Chinese): {meaning}",
            max_tokens=200, response_format={"type": "json_object"},
        )
        data = _json.loads(resp.choices[0].message.content or "{}")
        ex = data.get("example") or {}
        ph = data.get("phrase") or {}
        return {"example": {"en": str(ex.get("en", "")).strip(), "zh": str(ex.get("zh", "")).strip()},
                "phrase": {"en": str(ph.get("en", "")).strip(), "zh": str(ph.get("zh", "")).strip()}}
    except Exception as e:  # noqa: BLE001
        logger.warning("[例句短语] %s 失败: %s", word, e)
        return {"example": {"en": "", "zh": ""}, "phrase": {"en": "", "zh": ""}}


async def _gen_images_for(db: AsyncSession, w: VocabularyWord, cfg: dict | None = None) -> list[str]:
    """按配置生成配图(可选AI视觉场景)；并补充贴合图片的例句+短语(写到 w)。"""
    cfg = cfg or await get_image_config(db)
    meaning = _primary_meaning(w)
    pos = _pos_of(w)
    brief = ""
    if cfg.get("use_ai_prompt"):
        brief = await _ai_visual_brief(w.word, meaning, pos)
    prompts = _build_prompts(cfg, word=w.word, meaning=meaning,
                             n=int(cfg.get("images_per_word", 1)), brief=brief)
    urls: list[str] = []
    for p in prompts:
        u = await vocab_media_provider.t2i_to_cos(p, label=w.word)
        if u:
            urls.append(u)
    # 例句(先贴合图片意思) + 短语：缺失时补充；并预生成语音(火山→COS缓存)写入 JSONB
    ep = await _ai_example_phrase(w.word, meaning, pos, brief)
    if ep["example"]["en"]:
        ex = dict(ep["example"])
        ex["audio"] = await _tts_cos(ex["en"])
        w.examples = [ex]
    if ep["phrase"]["en"]:
        ph = dict(ep["phrase"])
        ph["audio"] = await _tts_cos(ph["en"])
        w.phrases = [ph]
    # 单词发音：预生成并写库，供原词力通 + AI口语-词力通共用
    if not w.word_audio_url:
        wa = await _tts_cos(w.word)
        if wa:
            w.word_audio_url = wa
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


# ── 动图 GIF(A 方案:动词/动作词关键帧,复用腾讯 Img2Img 保一致 + Pillow 拼 GIF)──────
async def _ai_motion_frames(word: str, meaning: str, pos: str) -> list[str] | None:
    """判定该词是否宜用动图(动作/移动/过程/时间变化),是则给 3 帧连续动作场景(首→中→末,
    同一人物/场景只推进姿势)。静态词(名词/形容词/静态状态)返回 None。走 fast 档。"""
    if llm_provider.is_llm_dev_mode():
        return [f"a child starting to {word}", f"a child doing {word}",
                f"a child finishing {word}"] if (pos or "").lower().startswith(("v", "动")) else None
    system = (
        "Decide whether an English word/phrase is best taught with a short ANIMATION (an action, "
        "movement, process or change over time) rather than one static picture. Concrete nouns, "
        "adjectives and static states do NOT need animation.\n"
        "If it needs animation, describe a 3-frame sequence (beginning → middle → end) of ONE consistent "
        "character in ONE consistent setting performing the action — each frame is ONE concrete visible "
        "moment, only the pose/action progresses between frames. Describe only what is visible. "
        "No text/letters in the image, no style words.\n"
        'Output strict JSON: {"animate": true|false, "frames": ["frame1 scene","frame2 scene","frame3 scene"]}. '
        "If animate is false, frames = [].")
    d = await llm_provider.complete_json(
        system_prompt=system, user_prompt=f"Word/phrase: {word}\nPOS: {pos}\nMeaning (Chinese): {meaning}",
        max_tokens=400, model=llm_provider.fast_model(), feature="vocab_gif_frames",
        validate=lambda x: "animate" in x)
    if not d or not d.get("animate"):
        return None
    frames = [str(f).strip() for f in (d.get("frames") or []) if str(f).strip()]
    return frames if len(frames) >= 2 else None


async def generate_gif_for_word(db: AsyncSession, *, word_id: uuid.UUID) -> tuple[VocabularyWord, bool]:
    """给动作/过程类词生成关键帧 GIF:首帧 T2I → 后续帧 Img2Img 从首帧演进(保人物/风格一致)→
    Pillow 拼 GIF 存 COS。返回 (word, animated);animated=False 表示该词无需动图(静态图即可)。"""
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    frames_desc = await _ai_motion_frames(w.word, _primary_meaning(w), _pos_of(w))
    if not frames_desc:
        return w, False
    cfg = await get_image_config(db)
    style = (cfg.get("styles") or [""])[0]
    suffix = "One clear consistent character, clean plain background, NO text/letters/numbers."
    first = f"{frames_desc[0]} {suffix}" + (f" Style: {style}." if style else "")
    url0 = await vocab_media_provider.t2i_to_cos(first, label=w.word)
    if not url0:
        return w, True   # 需要动图但首帧生成失败
    urls = [url0]
    for fd in frames_desc[1:]:
        u = await vocab_media_provider.i2i_to_cos(f"{fd} {suffix}", url0, label=w.word, strength=0.6)
        urls.append(u or url0)
    gif = await vocab_media_provider.frames_to_gif_cos(urls, label=w.word)
    if gif:
        w.gif_url = gif
        w.media_status = "draft"
        await db.flush()
    return w, True


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


async def backfill_audio(db: AsyncSession, *, limit: int = 500) -> dict:
    """给已生成 例句/短语/单词 但缺音频的词补预生成语音(火山→COS)，写回 JSONB / word_audio_url。

    幂等：已有 audio 的项跳过；供原词力通 + AI口语-词力通共用同一缓存直链。
    """
    rows = (await db.execute(select(VocabularyWord).limit(limit))).scalars().all()
    scanned = filled = 0
    for w in rows:
        changed = False
        exs = w.examples if isinstance(w.examples, list) else []
        new_ex = []
        for it in exs:
            if isinstance(it, dict) and it.get("en") and not it.get("audio"):
                it = {**it, "audio": await _tts_cos(str(it["en"]))}
                if it["audio"]:
                    changed = True
            new_ex.append(it)
        if changed:
            w.examples = new_ex
        ph_changed = False
        phs = w.phrases if isinstance(w.phrases, list) else []
        new_ph = []
        for it in phs:
            if isinstance(it, dict) and it.get("en") and not it.get("audio"):
                it = {**it, "audio": await _tts_cos(str(it["en"]))}
                if it["audio"]:
                    ph_changed = True
            new_ph.append(it)
        if ph_changed:
            w.phrases = new_ph
            changed = True
        if not w.word_audio_url:
            wa = await _tts_cos(w.word)
            if wa:
                w.word_audio_url = wa
                changed = True
        scanned += 1
        if changed:
            filled += 1
    await db.flush()
    return {"scanned": scanned, "filled": filled}


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


async def delete_words(db: AsyncSession, *, word_ids: list) -> dict:
    """彻底删除词条(不可恢复)。先清无 CASCADE 的阻断引用(课程单元词/学习记录/发音日志),
    再删词——其余引用(student_vocab_candidates/vocab_node/vocab_question/vocab_wrong/
    vocab_list_item)为 ON DELETE CASCADE 自动清。返回删除数。"""
    from sqlalchemy import text as _text
    if not word_ids:
        return {"deleted": 0}
    ids = [str(w) for w in word_ids]
    # 阻断性引用(NO ACTION)先手动清
    for tbl in ("curriculum_words", "vocabulary_learning", "vocab_pron_logs"):
        await db.execute(
            _text(f"DELETE FROM {tbl} WHERE word_id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids})
    r = await db.execute(
        _text("DELETE FROM vocabulary_words WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids})
    await db.commit()
    return {"deleted": r.rowcount or 0}


async def list_words_for_media_review(
    db: AsyncSession, *, media_status: str = "draft", skip: int = 0, limit: int = 20,
    q: str | None = None,
    textbook: str | None = None, grade: str | None = None, semester: str | None = None,
    unit_id=None,
) -> tuple[list[VocabularyWord], int]:
    base = select(VocabularyWord)
    if media_status:                       # 空=全部状态(不过滤)
        base = base.where(VocabularyWord.media_status == media_status)
    if q:                                  # 全库按单词模糊搜
        base = base.where(VocabularyWord.word.ilike(f"%{q}%"))
    # 教材版本/年级/上下册/单元:经 curriculum_words → curriculum_units 归属(EXISTS)
    if textbook or grade or semester or unit_id:
        from app.models.d4_knowledge import CurriculumWord, CurriculumUnit
        ex = (select(CurriculumWord.word_id)
              .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
              .where(CurriculumWord.word_id == VocabularyWord.id))
        if unit_id:
            ex = ex.where(CurriculumWord.unit_id == unit_id)
        if textbook:
            ex = ex.where(CurriculumUnit.textbook_version == textbook)
        if grade:
            ex = ex.where(CurriculumUnit.grade == grade)
        if semester:
            ex = ex.where(CurriculumUnit.semester == semester)
        base = base.where(ex.exists())
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabularyWord.word).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total
