"""词力通图背单词媒体业务（P1 / D-101）。

generate_for_word：英文描述（LLM，dev-mock 出固定文本）+ 多图 + 双音频（provider dev-mock），
写库默认 media_status='draft'，运营审核后 published。
"""
from __future__ import annotations

import hashlib
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
from app.services import (
    llm_provider, tts_service, vocab_media_asset_service, vocab_media_provider)


async def _tts_cos(text: str, voice: str | None = None) -> str:
    """火山 TTS → COS 缓存直链；voice 指定固定音色(空=按词哈希选男/女);失败/COS-dev 返回空串。"""
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return (await tts_service.get_or_create_audio_url(text, voice=voice or None)) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("[词力通TTS] %s 失败: %s", text[:20], e)
        return ""


# 音色中文名(默认池;自定义音色无映射则显 id)。gender 供前端分组。
_VOICE_ZH: dict[str, dict] = {
    "en_male_tim_uranus_bigtts": {"label": "Tim·英式男声", "gender": "英男"},
    "en_female_dacey_uranus_bigtts": {"label": "Dacey·英式女声", "gender": "英女"},
    "en_female_stokie_uranus_bigtts": {"label": "Stokie·英式女声", "gender": "英女"},
    "zh_male_wennuanahu_uranus_bigtts": {"label": "温暖阿虎", "gender": "男"},
    "zh_male_jieshuonansheng_mars_bigtts": {"label": "解说男声", "gender": "男"},
    "zh_female_shuangkuaisisi_moon_bigtts": {"label": "爽快思思", "gender": "女"},
    "zh_female_wanwanxiaohe_moon_bigtts": {"label": "湾湾小何", "gender": "女"},
}


# 词力通音色下拉隐藏的音色(不删全局 TTS 池,只是不在此处供选)
_VOICE_EXCLUDE = {"en_female_dacey_uranus_bigtts"}


def voice_label(vid: str) -> str:
    m = _VOICE_ZH.get(vid)
    return f"{m['label']}（{m['gender']}）" if m else vid


async def _curated_voice_ids(db: AsyncSession) -> list[str]:
    """词力通下拉里实际可选的音色 id(男/女池去重、排除隐藏项)。"""
    pools = await tts_service.get_voices(db)
    return [v for v in dict.fromkeys((pools.get("male") or []) + (pools.get("female") or []))
            if v not in _VOICE_EXCLUDE]


def _auto_voice(word: str, curated: list[str]) -> str | None:
    """自动音色:在下拉那几个音色里按词稳定随机(同词固定→音频可缓存;不同词分散)。"""
    if not curated:
        return None
    idx = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % len(curated)
    return curated[idx]


async def voice_options(db: AsyncSession) -> dict:
    """可选音色列表(男/女池,排除隐藏项) + 当前选用。供后台下拉(中文名 + id)。"""
    ids = await _curated_voice_ids(db)
    cfg = await get_image_config(db)
    return {"voices": [{"id": v, "label": voice_label(v),
                        "gender": _VOICE_ZH.get(v, {}).get("gender", "")} for v in ids],
            "selected": cfg.get("voice") or ""}


async def set_word_voice(db: AsyncSession, *, voice: str, updated_by) -> dict:
    """只更新「固定音色」(保留其余配置)。voice 为空=恢复按词哈希选男/女。返回完整配置。"""
    cfg = dict(await get_image_config(db))
    cfg["voice"] = str(voice or "").strip()
    return await set_image_config(db, config=cfg, updated_by=updated_by)

# ── 配图提示词配置中心（system_configs，可后台配）─────────────────────────────
_IMG_KEY = "vocab_image_gen"
_IMG_TTL = 60.0
_img_cache: dict = {"data": None, "ts": 0.0}

_DEF_PRIMARY = (
    'A clear, simple illustration that visually conveys the MEANING of the English word/phrase '
    '"{word}" — {meaning}. Depict the concrete object, scene or action that unambiguously expresses '
    'this meaning. Include a person ONLY if the meaning itself is a person, a feeling, or a human '
    'action — then show their expression/posture and its cause; for objects, food, quantities, '
    'places and things show ONLY those, with NO people in the image. '
    'One clear focal subject, clean plain background. '
    'Absolutely NO text, letters, numbers or words anywhere in the image.'
)
# 旧默认(会诱导画小孩/词义表达差):存量配置里若仍是其中任一句,自动升级为最新 _DEF_PRIMARY(不误伤自定义)
_OLD_PRIMARY = (
    'A clear, simple illustration that obviously represents the English word "{word}" '
    '({meaning}), for children learning English vocabulary. Single clear subject, clean '
    'plain background, NO text, letters or numbers anywhere in the image.'
)
# 上一版默认(feelings/abstract 无条件"show a character",仍爱塞小孩)→ 一并自愈升级
_PREV_PRIMARY = (
    'A clear, simple illustration that visually conveys the MEANING of the English word/phrase '
    '"{word}" — {meaning}. Depict a concrete scene, object or action that unambiguously expresses '
    'this meaning; for feelings or abstract words show a character whose facial expression, posture '
    'and the surrounding situation clearly convey it, together with the object causing it. '
    'One clear focal subject, clean plain background. Do NOT draw a random generic child. '
    'Absolutely NO text, letters, numbers or words anywhere in the image.'
)
_UPGRADABLE_PRIMARY = {_OLD_PRIMARY.strip(), _PREV_PRIMARY.strip()}
_DEF_STYLES = [
    "flat vector illustration, bright cheerful colors",
    "cute kawaii cartoon style, soft pastel colors",
    "simple watercolor illustration, gentle warm tones",
    "clean minimalist illustration with light soft shading",
    "friendly rounded 3D render, soft studio lighting",
]


def _default_img_config() -> dict:
    # style: 固定风格(为空=每张从 styles 随机);voice: 固定音色(为空=按词哈希选男/女)
    return {"batch_size": 20, "images_per_word": 1, "use_ai_prompt": True,
            "primary": _DEF_PRIMARY, "styles": list(_DEF_STYLES), "style": "", "voice": ""}


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
        if sp and sp not in _UPGRADABLE_PRIMARY:
            cfg["primary"] = sp
        if isinstance(saved.get("styles"), list):
            s = [str(x).strip() for x in saved["styles"] if str(x).strip()]
            if s:
                cfg["styles"] = s
        if "style" in saved:
            cfg["style"] = str(saved.get("style") or "").strip()
        if "voice" in saved:
            cfg["voice"] = str(saved.get("voice") or "").strip()
    return cfg


# 「生成画面描述提示词」用的系统指令(meta-prompt)默认值。后台可编辑/保存/回滚(见 get/set_brief_prompt)。
_DEF_BRIEF_SYSTEM = (
    "Design ONE concrete scene for a text-to-image model so a learner instantly grasps the word's MEANING. "
    "Output exactly ONE short English sentence, describing only what is visible, specific to this meaning. "
    "Show a person ONLY if the word is about a person, a feeling, or a human action; for objects, food, "
    "quantities, places and things show only the thing (make any amount obvious) with NO people. "
    "No text or numbers in the image, no style words, no explanation."
)
_BRIEF_KEY = "vocab_image_brief_prompt"


async def get_brief_prompt(db: AsyncSession) -> dict:
    """取「生成画面描述」用的系统指令 + 历史版本。未配则用默认。返回 {current, history:[{prompt,at}]}。"""
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _BRIEF_KEY))).scalar_one_or_none()
    v = row.value if row is not None else None
    if not isinstance(v, dict):
        return {"current": _DEF_BRIEF_SYSTEM, "history": []}
    cur = (str(v.get("current") or "").strip()) or _DEF_BRIEF_SYSTEM
    hist = v.get("history") if isinstance(v.get("history"), list) else []
    return {"current": cur, "history": hist}


async def set_brief_prompt(db: AsyncSession, *, prompt: str, updated_by, at: str) -> dict:
    """保存新指令:旧版压入 history(去重、最多留 20 条)。空则回默认。"""
    prompt = (prompt or "").strip() or _DEF_BRIEF_SYSTEM
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _BRIEF_KEY))).scalar_one_or_none()
    old, hist = None, []
    if row is not None and isinstance(row.value, dict):
        old = str(row.value.get("current") or "").strip()
        hist = row.value.get("history") if isinstance(row.value.get("history"), list) else []
    if old and old != prompt:
        hist = ([{"prompt": old, "at": at}] + [h for h in hist if h.get("prompt") != old])[:20]
    value = {"current": prompt, "history": hist}
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_BRIEF_KEY, value=value,
                            description="词力通配图-画面描述生成指令(meta-prompt,含历史)", updated_by=updated_by))
    else:
        row.value, row.updated_by = value, updated_by
    await db.flush()
    return value


async def _ai_visual_brief(word: str, meaning: str, pos: str, system: str | None = None) -> str:
    """用 LLM 把词(尤其抽象词/虚词/短语)转成一句"可画的具体视觉场景",提升图片可理解性。
    system=生成指令(不传则用默认);由调用方从后台配置取当前版本传入。空/过短则重试一次。"""
    if llm_provider.is_llm_dev_mode():
        return ""   # dev-mock:不增强,走主模板
    system = system or _DEF_BRIEF_SYSTEM
    up = f"Word/phrase: {word}\nPart of speech: {pos}\nMeaning (Chinese): {meaning}"
    for _ in range(2):
        try:
            # 关推理(disable_thinking):brief 是"一句话画面描述"的简单任务,v4-flash 若开推理会对
            # 抽象词想十几秒甚至吃满 token 返回空(慢且失败)。关思考后 ~1s 稳定出结果,256 token 足够。
            resp = await llm_provider.chat_completion(
                system_prompt=system, user_prompt=up, max_tokens=256,
                model=llm_provider.fast_model(), feature="vocab_image_brief",
                disable_thinking=True)
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


async def set_image_style(db: AsyncSession, *, style: str, updated_by) -> dict:
    """只更新「固定风格」(保留其余配置)。style 为空=恢复随机。返回完整配置。"""
    cfg = dict(await get_image_config(db))
    cfg["style"] = str(style or "").strip()
    return await set_image_config(db, config=cfg, updated_by=updated_by)


def _build_prompts(cfg: dict, *, word: str, meaning: str, n: int, brief: str = "") -> list[str]:
    """(AI视觉场景 brief +) 主要要求(固定模板) + 次要随机风格 → n 条提示词。"""
    try:
        base = cfg["primary"].format(word=word, meaning=meaning or word)
    except Exception:  # noqa: BLE001 模板占位写错时退化
        base = f'{cfg["primary"]} word: "{word}".'
    if brief:
        base = f"{brief} {base}"   # AI 生成的可画场景放最前，主要要求作约束
    fixed = str(cfg.get("style") or "").strip()
    if fixed:                       # 后台选定固定风格 → 所有图都用它(不再随机)
        picks = [fixed] * n
    else:
        styles = cfg.get("styles") or [""]
        picks = random.sample(styles, k=min(n, len(styles))) if len(styles) >= n else \
            [random.choice(styles) for _ in range(n)]
    return [f"{base} Style: {s}." if s else base for s in picks]


def _primary_meaning(w: VocabularyWord) -> str:
    d = w.definitions
    if isinstance(d, list) and d and isinstance(d[0], dict):
        # definitions 有两种历史格式:{meaning,pos} 与 {zh,part_of_speech},两个键都认
        return str(d[0].get("meaning") or d[0].get("zh") or "")
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
        max_tokens=200, model=llm_provider.fast_model(), disable_thinking=True,
        feature="vocab_en_desc")
    return (resp.choices[0].message.content or "").strip()


def _pos_of(w: VocabularyWord) -> str:
    d = w.definitions
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return str(d[0].get("pos") or d[0].get("part_of_speech") or "")
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
            model=llm_provider.fast_model(), disable_thinking=True, feature="vocab_example",
        )
        data = _json.loads(resp.choices[0].message.content or "{}")
        ex = data.get("example") or {}
        ph = data.get("phrase") or {}
        return {"example": {"en": str(ex.get("en", "")).strip(), "zh": str(ex.get("zh", "")).strip()},
                "phrase": {"en": str(ph.get("en", "")).strip(), "zh": str(ph.get("zh", "")).strip()}}
    except Exception as e:  # noqa: BLE001
        logger.warning("[例句短语] %s 失败: %s", word, e)
        return {"example": {"en": "", "zh": ""}, "phrase": {"en": "", "zh": ""}}


async def suggest_image_brief(db: AsyncSession, *, word_id: uuid.UUID,
                              system: str | None = None) -> str:
    """给某词返回一条 AI 建议的「画面描述提示词」(不出图),供后台弹框按需生成/编辑。
    system=生成指令(前端可传未保存的编辑版预览);不传则用后台已保存的当前指令。"""
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    sysp = system if (system and system.strip()) else (await get_brief_prompt(db))["current"]
    return await _ai_visual_brief(w.word, _primary_meaning(w), _pos_of(w), system=sysp)


async def _gen_images_for(db: AsyncSession, w: VocabularyWord, cfg: dict | None = None,
                          brief_override: str | None = None,
                          do_images: bool = True, do_audio: bool = True) -> list[str]:
    """按配置生成配图(可选AI视觉场景)+ 贴合图片的例句/短语(写到 w)。
    brief_override 非 None 时用它当画面描述(人工编辑),不再调 AI。
    do_images=False 跳过出图/例句(保留现有);do_audio=False 跳过所有 TTS(保留现有音频)。"""
    cfg = cfg or await get_image_config(db)
    meaning = _primary_meaning(w)
    pos = _pos_of(w)
    # 音色:配了固定音色→全用它;否则在页面下拉那几个音色里按词稳定随机(不再用全池男/女)
    voice = (cfg.get("voice") or "").strip() or None
    if not voice and do_audio:
        voice = _auto_voice(w.word, await _curated_voice_ids(db))
    urls: list[str] = []
    if do_images:
        brief = ""
        if brief_override is not None:
            brief = brief_override.strip()
        elif cfg.get("use_ai_prompt"):
            sysp = (await get_brief_prompt(db))["current"]
            brief = await _ai_visual_brief(w.word, meaning, pos, system=sysp)
        prompts = _build_prompts(cfg, word=w.word, meaning=meaning,
                                 n=int(cfg.get("images_per_word", 1)), brief=brief)
        for p in prompts:
            u = await vocab_media_provider.t2i_to_cos(p, label=w.word)
            if u:
                urls.append(u)
        if urls:   # 记为新图片版本(不覆盖历史),带当时风格+提示词,自动选用
            await vocab_media_asset_service.record_assets(
                db, word_id=w.id, kind="image", urls=urls,
                style=(cfg.get("style") or "随机"), prompt=(brief or None))
        # 例句(先贴合图片意思) + 短语；语音仅在 do_audio 时预生成(火山→COS缓存)
        ep = await _ai_example_phrase(w.word, meaning, pos, brief)
        if ep["example"]["en"]:
            ex = dict(ep["example"])
            if do_audio:
                ex["audio"] = await _tts_cos(ex["en"], voice)
            w.examples = [ex]
        if ep["phrase"]["en"]:
            ph = dict(ep["phrase"])
            if do_audio:
                ph["audio"] = await _tts_cos(ph["en"], voice)
            w.phrases = [ph]
    # 单词发音：do_audio 时(重)生成，记为新音频版本(不覆盖历史,自动选用→同步 word_audio_url)
    if do_audio:
        wa = await _tts_cos(w.word, voice)
        if wa:
            await vocab_media_asset_service.record_assets(
                db, word_id=w.id, kind="audio", urls=[wa])
    return urls


async def generate_for_word(db: AsyncSession, *, word_id: uuid.UUID,
                            brief_override: str | None = None,
                            do_images: bool = True, do_audio: bool = True) -> VocabularyWord:
    """生成词条媒体。do_images/do_audio 控制是否(重)生成图片/音频——批量时对已有资源可跳过。"""
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    if not (do_images or do_audio):
        return w                              # 图片、音频都跳过 → 无事可做
    if do_images:
        meaning = _primary_meaning(w)
        w.en_description = await _gen_en_description(w.word, meaning)
    imgs = await _gen_images_for(db, w, brief_override=brief_override,
                                 do_images=do_images, do_audio=do_audio)
    if do_images and imgs:
        w.image_urls = imgs
    w.media_status = "draft"
    await db.flush()
    return w


async def ensure_word_media(db: AsyncSession, *, word_id: uuid.UUID) -> VocabularyWord | None:
    """单词媒体「即时兜底」:该词若没有已发布媒体(配图),即时生成图/音/英文释义/例句并
    **直接发布**(学生触发,全学生共享;结果落词条,同词后续命中不再付费——暂存铁律)。
    已有已发布配图 → 幂等跳过。供长难句/作业里「加入学习」时对无媒体的词即时补齐。"""
    w = (await db.execute(select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        return None
    if str(w.media_status) == "published" and isinstance(w.image_urls, list) and w.image_urls:
        return w                                  # 已有媒体,不重复生成
    await generate_for_word(db, word_id=word_id, do_images=True, do_audio=True)
    w.media_status = "published"                  # 学生即时生成 → 直接可见(素材已记版本,admin 仍可复核)
    w.media_origin = "student"                    # 标记来源:学生端「加入学习」即时生成,供后台过滤复核
    await db.commit()
    await db.refresh(w)
    return w


async def generate_i2i_for_word(db: AsyncSession, *, word_id: uuid.UUID,
                                source_url: str | None = None, source_b64: str | None = None,
                                prompt: str = "", strength: float = 0.6) -> VocabularyWord:
    """图生图:上传图/图片地址当原图 → 腾讯图生图出变体。原图与结果都记为该词的图片版本
    (原图入历史不选用,结果自动选用为当前)。"""
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    # 解析原图 → COS 持久链
    if source_b64:
        import base64 as _b64
        raw = _b64.b64decode(source_b64.split(",")[-1])   # 去掉可能的 data:...;base64, 前缀
        src = await vocab_media_provider.persist_image_bytes_to_cos(raw)
    elif source_url and source_url.strip():
        src = await vocab_media_provider.fetch_image_to_cos(source_url.strip())
    else:
        raise AppError(code=400, message="请提供原图(上传或图片地址)")
    if not src:
        raise AppError(code=500, message="原图转存失败(检查 COS 配置)")
    # 原图记为版本(入历史,不选用)并「先落库」——即便后续图生图失败,原图也已保留
    await vocab_media_asset_service.record_assets(
        db, word_id=w.id, kind="image", urls=[src], style="原图", prompt="图生图输入原图",
        select_new=False)
    await db.commit()
    # 图生图 → 结果
    result = await vocab_media_provider.i2i_to_cos(prompt or "", src, label=w.word, strength=strength)
    if not result:
        raise AppError(code=500, message="图生图失败,请重试(原图已存为版本,可在「版本」里查看/选用)")
    # 结果记为版本并选用(→ 同步 image_urls)
    await vocab_media_asset_service.record_assets(
        db, word_id=w.id, kind="image", urls=[result], style="图生图", prompt=(prompt or None))
    w.media_status = "draft"
    await db.flush()
    return w


# ── 动图(动词/动作词:现有静态配图当首帧 + 智谱 CogVideoX-Flash 图生视频,真运动)──────
async def _ai_motion_desc(word: str, meaning: str, pos: str) -> str | None:
    """判定该词是否宜用动图(动作/移动/过程/时间变化),是则给「一句该图里要发生的可见运动」的
    英文描述(喂图生视频,让静态配图动起来)。静态词(名词/形容词/静态状态)返回 None。走 fast 档。"""
    if llm_provider.is_llm_dev_mode():
        return (f"the subject performs the action '{word}' with clear, visible, natural motion"
                if (pos or "").lower().startswith(("v", "动")) else None)
    system = (
        "Decide whether an English word/phrase is best taught with a short ANIMATION (an action, "
        "movement, process or change over time) rather than one static picture. Concrete nouns, "
        "adjectives and static states do NOT need animation.\n"
        "If it needs animation, write ONE English sentence describing the visible MOTION to apply to a "
        "still image so it comes alive — what moves, how it moves, the direction/gesture of the action. "
        "Keep the same single subject and setting; describe only visible movement (no style words, no text).\n"
        'Output strict JSON: {"animate": true|false, "motion": "one motion sentence"}. '
        "If animate is false, motion = \"\".")
    d = await llm_provider.complete_json(
        system_prompt=system, user_prompt=f"Word/phrase: {word}\nPOS: {pos}\nMeaning (Chinese): {meaning}",
        max_tokens=400, escalate_ceiling=800, model=llm_provider.fast_model(),
        feature="vocab_video_motion", validate=lambda x: "animate" in x)
    if not d or not d.get("animate"):
        return None
    motion = str(d.get("motion") or "").strip()
    return motion or None


async def generate_gif_for_word(db: AsyncSession, *, word_id: uuid.UUID) -> tuple[VocabularyWord, str]:
    """给动作/过程类词生成动图:用该词现有静态配图当首帧 + AI 动作描述 → 智谱 CogVideoX-Flash
    图生视频(真运动)→ 存 COS,写入 gif_url(实为 mp4 直链)。缺静态配图时先 T2I 生成一张当首帧。

    返回 (word, status):
      - "skip"      该词无需动图(名词/静态词,静态图即可);
      - "generated" 本次真生成了新动图并已写库;
      - "failed"    需要动图但生成失败(首帧或图生视频失败,如免费档限流)——不改动 gif_url。
    """
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    motion = await _ai_motion_desc(w.word, _primary_meaning(w), _pos_of(w))
    if not motion:
        return w, "skip"
    # 首帧:优先复用已生成的静态配图,避免重复付费;没有才现生成一张
    base = next((u for u in (w.image_urls or []) if u), None)
    if not base:
        cfg = await get_image_config(db)
        style = (cfg.get("styles") or [""])[0]
        prompt = (f"A clear, simple illustration showing the meaning of '{w.word}' ({_primary_meaning(w)}). "
                  "One clear subject, clean plain background, NO text/letters/numbers."
                  + (f" Style: {style}." if style else ""))
        base = await vocab_media_provider.t2i_to_cos(prompt, label=w.word)
        if not base:
            return w, "failed"   # 需要动图但首帧生成失败
    video = await vocab_media_provider.i2v_to_cos(motion, base, label=w.word)
    if not video:
        return w, "failed"       # 需要动图但图生视频失败(勿让旧 gif_url 冒充成功)
    # 记为新 GIF 版本(不覆盖历史,自动选用→同步 gif_url)
    await vocab_media_asset_service.record_assets(
        db, word_id=w.id, kind="gif", urls=[video], prompt=(motion or None))
    w.media_status = "draft"
    await db.flush()
    return w, "generated"


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
    meaning: str | None = None,
    pos: str | None = None,
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
    # 中文词义/词性:写入首个 definition(统一 {meaning,pos});保留其余义项与键
    if meaning is not None or pos is not None:
        defs = list(w.definitions) if isinstance(w.definitions, list) else []
        d0 = dict(defs[0]) if defs and isinstance(defs[0], dict) else {}
        if meaning is not None:
            d0["meaning"] = meaning.strip()
            d0.pop("zh", None)                       # 去旧键,归一到 meaning
        if pos is not None:
            d0["pos"] = pos.strip()
            d0.pop("part_of_speech", None)
        defs = [d0] + defs[1:] if defs else [d0]
        w.definitions = defs
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
    q: str | None = None, media_origin: str | None = None,
    textbook: str | None = None, grade: str | None = None, semester: str | None = None,
    unit_id=None,
) -> tuple[list[VocabularyWord], int]:
    base = select(VocabularyWord)
    if media_status:                       # 空=全部状态(不过滤)
        base = base.where(VocabularyWord.media_status == media_status)
    if media_origin:                       # 'student'=学生端即时生成(待复核)
        base = base.where(VocabularyWord.media_origin == media_origin)
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
