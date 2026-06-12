"""AI 口语对话练习 service。

学生用微信同声传译插件做语音识别（或直接打字）→ 文本发到后端，
后端用 LLM 生成自然、难度适配的英文回复 + 轻量纠错，并用火山 TTS（按场景固定
男/女音色）合成回复语音，返回 COS 直链供小程序即点即播。

dev-mock：LLM 占位时走本地确定性回复，整条链路（含 H5 文本路径）可跑通。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.services import tts_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

logger = logging.getLogger(__name__)

# 预设场景：persona=AI 扮演角色英文说明；gender 决定 TTS 音色；opening=AI 开场白
_SCENARIOS: list[dict] = [
    {
        "key": "self_intro", "title": "自我介绍", "emoji": "🙋",
        "persona": "a friendly new classmate named Emma",
        "gender": "f",
        "opening": "Hi! I'm Emma, your new classmate. What's your name?",
    },
    {
        "key": "restaurant", "title": "餐厅点餐", "emoji": "🍔",
        "persona": "a polite waiter at a fast-food restaurant",
        "gender": "m",
        "opening": "Welcome! What would you like to order today?",
    },
    {
        "key": "directions", "title": "问路指路", "emoji": "🗺️",
        "persona": "a kind local person helping a tourist find the way",
        "gender": "m",
        "opening": "Hello! You look a bit lost. Where do you want to go?",
    },
    {
        "key": "shopping", "title": "购物砍价", "emoji": "🛍️",
        "persona": "a cheerful shop assistant in a clothing store",
        "gender": "f",
        "opening": "Hi there! Are you looking for anything special today?",
    },
    {
        "key": "hobbies", "title": "聊聊爱好", "emoji": "🎨",
        "persona": "a curious friend named Leo who loves chatting about hobbies",
        "gender": "m",
        "opening": "Hey! So, what do you like to do in your free time?",
    },
    {
        "key": "school", "title": "校园生活", "emoji": "🏫",
        "persona": "a friendly exchange student named Mia asking about school life",
        "gender": "f",
        "opening": "Hi! I just moved here. What's your school like?",
    },
]
_BY_KEY = {s["key"]: s for s in _SCENARIOS}

_LEVEL_BY_STAGE = {
    "primary": "elementary school (very simple words, present tense)",
    "junior": "junior high school (simple everyday English)",
    "senior": "senior high school (natural conversational English)",
}

# ── 口语场景配置中心（平台后台 system_configs 可配，进程内短缓存）─────────────
_SPK_KEY = "speaking_scenarios"
_SPK_TTL = 60.0
_spk_cache: dict = {"data": None, "ts": 0.0}

_DEF_WRONG_PROMPT = (
    "You are a patient, encouraging speaking coach helping the student practice "
    "the grammar/usage points they often get wrong. Stay friendly and on topic, "
    "keep replies to 1-2 short sentences, and gently correct related mistakes.")
_DEF_VOCAB_PROMPT = (
    "You are a cheerful word-practice buddy helping the student actually use the "
    "words they are learning. Keep replies short and naturally weave 1-2 target "
    "words into each reply.")
_DEF_SEM_PROMPT = (
    "You are a friendly tutor chatting about the student's current school unit. "
    "Keep replies to 1-2 short sentences and guide them to talk about the topic.")


def _def_preset_prompt(s: dict) -> str:
    return (f"You are {s['persona']}. Have a natural spoken-English conversation, "
            f"stay in character and on the scenario topic, keep replies to 1-2 short "
            f"sentences, and gently correct clear mistakes.")


def _default_config() -> dict:
    return {
        "special": {
            "wrong": {"enabled": True, "prompt": _DEF_WRONG_PROMPT},
            "vocab": {"enabled": True, "prompt": _DEF_VOCAB_PROMPT},
        },
        "preset": {s["key"]: {"enabled": True, "prompt": _def_preset_prompt(s)} for s in _SCENARIOS},
        "semester": {"enabled": True, "default_prompt": _DEF_SEM_PROMPT, "rules": {}},
    }


def _merge_config(saved: dict | None) -> dict:
    """把存档配置并到默认上（默认补全缺失项，保证结构完整）。"""
    cfg = _default_config()
    if not isinstance(saved, dict):
        return cfg
    sp = saved.get("special") or {}
    for k in ("wrong", "vocab"):
        if isinstance(sp.get(k), dict):
            cfg["special"][k]["enabled"] = bool(sp[k].get("enabled", True))
            if sp[k].get("prompt"):
                cfg["special"][k]["prompt"] = str(sp[k]["prompt"])
    pr = saved.get("preset") or {}
    for k, v in cfg["preset"].items():
        if isinstance(pr.get(k), dict):
            v["enabled"] = bool(pr[k].get("enabled", True))
            if pr[k].get("prompt"):
                v["prompt"] = str(pr[k]["prompt"])
    sm = saved.get("semester") or {}
    if isinstance(sm, dict):
        cfg["semester"]["enabled"] = bool(sm.get("enabled", True))
        if sm.get("default_prompt"):
            cfg["semester"]["default_prompt"] = str(sm["default_prompt"])
        if isinstance(sm.get("rules"), dict):
            cfg["semester"]["rules"] = {str(k): str(v) for k, v in sm["rules"].items() if v}
    return cfg


async def get_speaking_config(db: AsyncSession) -> dict:
    now = time.time()
    if _spk_cache["data"] is not None and now - _spk_cache["ts"] < _SPK_TTL:
        return _spk_cache["data"]
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _SPK_KEY)
    )).scalar_one_or_none()
    cfg = _merge_config(row.value if row is not None else None)
    _spk_cache["data"] = cfg
    _spk_cache["ts"] = now
    return cfg


async def set_speaking_config(db: AsyncSession, *, config: dict, updated_by) -> dict:
    value = _merge_config(config)
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _SPK_KEY)
    )).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_SPK_KEY, value=value,
            description="口语对话场景配置(启用开关+AI提示词)", updated_by=updated_by,
        ))
    else:
        row.value = value
        row.updated_by = updated_by
    await db.flush()
    _spk_cache["data"] = None
    return value


async def semester_scope_tree(db: AsyncSession, *, limit: int = 500) -> list[dict]:
    """学期分级规则编辑用：列出有单元的 教材/年级/学期/单元（含全路径 key）。"""
    from app.models.d4_knowledge import CurriculumUnit
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.textbook_version, CurriculumUnit.grade,
               CurriculumUnit.semester, CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.textbook_version, CurriculumUnit.grade,
                  CurriculumUnit.semester, CurriculumUnit.unit_no)
        .limit(limit)
    )).all()
    return [
        {"unit_id": str(r[0]), "textbook_version": r[1], "grade": r[2],
         "semester": str(r[3]), "unit_no": r[4], "unit_title": r[5]}
        for r in rows
    ]


def _resolve_sem_prompt(cfg: dict, *, tv: str, grade: str, sem: str, unit_id: str) -> str:
    """学期场景提示词：单元→学期→年级→教材→默认，就近命中，不套用上级。"""
    rules = (cfg.get("semester") or {}).get("rules") or {}
    for key in (f"unit:{unit_id}", f"semester:{tv}/{grade}/{sem}",
                f"grade:{tv}/{grade}", f"textbook:{tv}"):
        if rules.get(key):
            return str(rules[key])
    return (cfg.get("semester") or {}).get("default_prompt") or _DEF_SEM_PROMPT


async def list_scenarios(db: AsyncSession) -> list[dict]:
    cfg = await get_speaking_config(db)
    pr = cfg["preset"]
    return [
        {"key": s["key"], "title": s["title"], "emoji": s["emoji"],
         "opening": s["opening"], "tag": "preset"}
        for s in _SCENARIOS
        if pr.get(s["key"], {}).get("enabled", True)
    ]


def get_scenario(key: str) -> dict | None:
    return _BY_KEY.get(key)


def _gender_for_key(key: str) -> str:
    return "f" if int(hashlib.md5(key.encode()).hexdigest(), 16) % 2 else "m"


async def _student_prefs(db: AsyncSession, student_id) -> tuple[str | None, str | None, str | None]:
    from app.models.d1_users import User
    row = (await db.execute(
        select(User.preferred_textbook_version, User.preferred_grade, User.preferred_semester)
        .where(User.id == student_id)
    )).first()
    return (row[0], row[1], row[2]) if row else (None, None, None)


async def _semester_units(db: AsyncSession, student_id, *, limit: int = 3) -> list[dict]:
    """当前学期前若干单元 → 每单元一个对话场景。"""
    tv, grade, sem = await _student_prefs(db, student_id)
    if not (tv and grade and sem):
        return []
    from app.models.d4_knowledge import CurriculumUnit
    units = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.unit_title)
        .where(CurriculumUnit.textbook_version == tv, CurriculumUnit.grade == grade,
               CurriculumUnit.semester == sem)
        .order_by(CurriculumUnit.unit_no).limit(limit)
    )).all()
    return [
        {"key": f"sem:{uid}", "title": (title or "本单元")[:18], "emoji": "📖",
         "opening": f"Let's chat about \"{title}\". What do you know about it?",
         "tag": "custom", "source": "学期内容"}
        for uid, title in units
    ]


async def _unit_kp_names(db: AsyncSession, unit_id) -> list[str]:
    from app.models.d4_knowledge import KnowledgePoint, UnitKnowledgePoint
    rows = (await db.execute(
        select(KnowledgePoint.name)
        .join(UnitKnowledgePoint, UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .where(UnitKnowledgePoint.unit_id == unit_id).limit(8)
    )).all()
    return [r[0] for r in rows if r[0]]


async def _vocab_words(db: AsyncSession, student_id, *, limit: int = 8) -> list[str]:
    """学生词力通在练（临近复习/未掌握）的单词。"""
    from app.models.d5_learning import VocabularyLearning, VocabularyWord
    rows = (await db.execute(
        select(VocabularyWord.word)
        .join(VocabularyLearning, VocabularyLearning.word_id == VocabularyWord.id)
        .where(VocabularyLearning.student_id == student_id)
        .order_by(VocabularyLearning.next_review_at.asc()).limit(limit)
    )).all()
    return [r[0] for r in rows if r[0]]


async def _wrong_kp_names(db: AsyncSession, student_id, *, limit: int = 5) -> list[str]:
    """学生错题关联的高频知识点。"""
    from sqlalchemy import func
    from app.models.d3_wrong_questions import WrongQuestion
    from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
    rows = (await db.execute(
        select(KnowledgePoint.name, func.count().label("c"))
        .join(WrongQuestionKnowledgePoint,
              WrongQuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .join(WrongQuestion, WrongQuestion.id == WrongQuestionKnowledgePoint.wrong_question_id)
        .where(WrongQuestion.student_id == student_id,
               WrongQuestion.is_mastered.is_(False))
        .group_by(KnowledgePoint.name).order_by(func.count().desc()).limit(limit)
    )).all()
    return [r[0] for r in rows if r[0]]


async def list_personalized(db: AsyncSession, student_id) -> list[dict]:
    """因材施教的个性化场景：学期内容 + 词力通在练 + 错题薄弱点（按后台开关过滤）。"""
    cfg = await get_speaking_config(db)
    out: list[dict] = []
    if cfg["semester"]["enabled"]:
        out.extend(await _semester_units(db, student_id))
    if cfg["special"]["vocab"]["enabled"]:
        words = await _vocab_words(db, student_id)
        if len(words) >= 3:
            out.append({
                "key": "vocab", "title": "词力通在练词", "emoji": "🔤",
                "opening": f"Time to use your new words! Can you make a sentence with \"{words[0]}\"?",
                "tag": "custom", "source": "词力通",
            })
    if cfg["special"]["wrong"]["enabled"]:
        wkps = await _wrong_kp_names(db, student_id)
        if wkps:
            out.append({
                "key": "wrong", "title": "错题薄弱点", "emoji": "🎯",
                "opening": "Let's practice the parts you found tricky. Ready when you are!",
                "tag": "custom", "source": "错题",
            })
    return out


async def resolve_scenario(db: AsyncSession, *, student_id, key: str) -> dict | None:
    """把场景 key 还原为完整场景（含 persona/gender/opening/focus）。

    个性化场景的 focus 在此从 DB 实时重建（无需服务端缓存）。
    """
    cfg = await get_speaking_config(db)
    preset = get_scenario(key)
    if preset is not None:
        prompt = (cfg["preset"].get(key, {}) or {}).get("prompt") or _def_preset_prompt(preset)
        return {**preset, "focus": "", "prompt": prompt}

    g = _gender_for_key(key)
    if key.startswith("sem:"):
        import uuid as _uuid
        try:
            unit_id = str(_uuid.UUID(key[4:]))
        except (ValueError, AttributeError):
            return None
        from app.models.d4_knowledge import CurriculumUnit
        row = (await db.execute(
            select(CurriculumUnit.unit_title, CurriculumUnit.textbook_version,
                   CurriculumUnit.grade, CurriculumUnit.semester)
            .where(CurriculumUnit.id == unit_id)
        )).first()
        if row is None:
            return None
        title, tv, grade, sem = row[0] or "this unit", row[1], row[2], row[3]
        kps = await _unit_kp_names(db, unit_id)
        focus = (f"The conversation topic is the school unit \"{title}\". "
                 + (f"Related language points: {', '.join(kps)}. " if kps else "")
                 + "Naturally guide the student to talk about this topic.")
        return {
            "key": key, "title": title[:18], "emoji": "📖", "gender": g,
            "persona": f"a friendly tutor named Sam chatting about the school topic \"{title}\"",
            "opening": f"Let's chat about \"{title}\". What do you know about it?",
            "focus": focus, "source": "学期内容",
            "targets": ([title] + kps)[:6], "target_kind": "topic",
            "prompt": _resolve_sem_prompt(cfg, tv=tv, grade=grade, sem=str(sem), unit_id=unit_id),
        }

    if key.startswith("words:"):
        # 指定单词专项（如评价里「再练未用到的词」）：词表编码在 key 中（| 分隔）
        words = [w.strip() for w in key[6:].split("|") if w.strip()][:8]
        if not words:
            return None
        focus = (f"Encourage the student to use these specific words: {', '.join(words)}. "
                 f"Weave 1-2 of them into each of your replies naturally.")
        return {
            "key": key, "title": "专项练词", "emoji": "🔤", "gender": g,
            "persona": "a cheerful word-practice buddy helping the student use target words",
            "opening": f"Let's practice these words: {', '.join(words)}. "
                       f"Can you use \"{words[0]}\" in a sentence?",
            "focus": focus, "source": "词力通", "targets": words, "target_kind": "word",
            "prompt": cfg["special"]["vocab"]["prompt"],
        }

    if key == "vocab":
        words = await _vocab_words(db, student_id)
        if not words:
            return None
        focus = (f"Encourage the student to use these words they are learning: "
                 f"{', '.join(words)}. Weave 1-2 of them into each of your replies naturally.")
        return {
            "key": "vocab", "title": "词力通在练词", "emoji": "🔤", "gender": g,
            "persona": "a cheerful word-practice buddy helping the student use new words",
            "opening": f"Time to use your new words! Can you make a sentence with \"{words[0]}\"?",
            "focus": focus, "source": "词力通", "targets": words, "target_kind": "word",
            "prompt": cfg["special"]["vocab"]["prompt"],
        }

    if key == "wrong":
        kps = await _wrong_kp_names(db, student_id)
        if not kps:
            return None
        focus = (f"The student has been making mistakes on: {', '.join(kps)}. "
                 f"Gently steer the conversation so they practice these points out loud, "
                 f"and correct related mistakes.")
        return {
            "key": "wrong", "title": "错题薄弱点", "emoji": "🎯", "gender": g,
            "persona": "a patient coach helping the student practice their tricky points",
            "opening": "Let's practice the parts you found tricky. Ready when you are!",
            "focus": focus, "source": "错题薄弱点", "targets": kps, "target_kind": "point",
            "prompt": cfg["special"]["wrong"]["prompt"],
        }

    return None


async def opening(
    db: AsyncSession, *, student_id, scenario_key: str, stage: str = "junior",
) -> dict:
    sc = await resolve_scenario(db, student_id=student_id, key=scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    speed = await tts_service.speed_for_stage_db(db, stage)
    voice = await tts_service.first_voice(db, sc["gender"])
    audio = await tts_service.get_or_create_audio_url(sc["opening"], voice=voice, speed=speed)
    return {
        "scenario": {"key": sc["key"], "title": sc["title"], "emoji": sc["emoji"]},
        "ai_text": sc["opening"],
        "ai_audio_url": audio or "",
    }


def _mock_reply(user_text: str) -> dict:
    """dev-mock：确定性、友好的英文回复 + 简单跟进问题（保证 H5 可测）。"""
    u = (user_text or "").strip()
    if not u:
        return {"reply": "Sorry, I didn't catch that. Could you say it again?",
                "correction": "", "translation": "抱歉，我没听清，能再说一遍吗？"}
    follow = "That's interesting! Can you tell me more?"
    if "?" in u:
        follow = "Good question! What do you think?"
    return {
        "reply": f"I see, you said: \"{u[:60]}\". {follow}",
        "correction": "",
        "translation": "（示例模式）我明白了，再多说一点吧！",
    }


async def reply(
    db: AsyncSession, *, student_id, scenario_key: str, history: list[dict], user_text: str,
    stage: str = "junior",
) -> dict:
    sc = await resolve_scenario(db, student_id=student_id, key=scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    user_text = (user_text or "").strip()[:500]

    if is_llm_dev_mode():
        data = _mock_reply(user_text)
    else:
        level = _LEVEL_BY_STAGE.get(stage, _LEVEL_BY_STAGE["junior"])
        focus = (sc.get("focus") or "").strip()
        # 角色/风格提示词来自后台配置（缺省回退 persona 模板）
        base = (sc.get("prompt") or "").strip() or (
            f"You are {sc.get('persona', 'a friendly tutor')}. Have a natural "
            f"spoken-English conversation, stay in character and on topic, keep replies "
            f"to 1-2 short sentences, and gently correct clear mistakes.")
        sys = (
            base + f" The student is a Chinese student at {level} level. "
            + "Always reply in 1-2 SHORT sentences and end by inviting them to keep talking. "
            + (f"Personalization: {focus} " if focus else "")
            + "Respond ONLY as compact JSON with keys: reply (your English line), "
            "correction (a short note on the student's mistake, or empty string), "
            "translation (a Chinese translation of your reply)."
        )
        convo = "\n".join(
            f"{'Student' if m.get('role') == 'user' else 'You'}: {m.get('text', '')}"
            for m in (history or [])[-8:]
        )
        usr = (f"Conversation so far:\n{convo}\n\nStudent: {user_text}\n\n"
               f"Reply now as JSON.")
        try:
            resp = await chat_completion(
                system_prompt=sys, user_prompt=usr, max_tokens=300,
                response_format={"type": "json_object"})
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:  # noqa: BLE001
            logger.warning("[Speaking] LLM 调用失败，回退 mock: %s", e)
            data = _mock_reply(user_text)

    ai_text = (data.get("reply") or "").strip() or "Let's keep practicing! Tell me more."
    speed = await tts_service.speed_for_stage_db(db, stage)
    voice = await tts_service.first_voice(db, sc["gender"])
    audio = await tts_service.get_or_create_audio_url(ai_text, voice=voice, speed=speed)
    return {
        "ai_text": ai_text,
        "ai_audio_url": audio or "",
        "correction": (data.get("correction") or "").strip(),
        "translation": (data.get("translation") or "").strip(),
    }


def _clamp_score(v, default=70) -> int:
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:  # noqa: BLE001
        return default


def _mock_summary(user_turns: list[str]) -> dict:
    """dev-mock：按学生发言条数/平均长度给确定性评价（H5 可测）。"""
    n = len(user_turns)
    avg = (sum(len(t.split()) for t in user_turns) / n) if n else 0
    base = min(95, 60 + n * 4 + int(avg))
    return {
        "overall": _clamp_score(base),
        "fluency": _clamp_score(base - 2),
        "grammar": _clamp_score(base - 5),
        "vocabulary": _clamp_score(base + 2),
        "highlights": ["敢于开口，完成了多轮对话", "用到了完整句子表达"][: max(1, min(2, n))],
        "improvements": ["可以尝试更长的句子和连接词（and/because）", "注意动词时态与单复数"],
        "encouragement": "练得不错，继续保持每天开口说英语！",
    }


def _focus_review(sc: dict, user_turns: list[str]) -> dict:
    """据本次场景的个性化目标(单词/薄弱点/单元)，点评"练到了什么、掌握如何"。

    单词类：按是否在发言中出现做确定性掌握判断；薄弱点/单元类：给专项练习提示。
    通用预设场景：返回空（前端不展示）。
    """
    source = sc.get("source") or ""
    targets = [t for t in (sc.get("targets") or []) if t]
    kind = sc.get("target_kind") or ""
    if not source or not targets:
        return {"focus_source": "", "focus_review": "", "focus_used": [], "focus_missed": []}

    if kind == "word":
        joined = " ".join(user_turns).lower()
        used = [w for w in targets if w.lower() in joined]
        missed = [w for w in targets if w.lower() not in joined]
        if used and not missed:
            note = f"太棒了！本次在练的 {len(used)} 个词都用上了，掌握得不错 👍"
        elif used:
            note = (f"本次用上了 {len(used)}/{len(targets)} 个在练词；"
                    f"还没用到「{'、'.join(missed[:4])}」，下次试着说说看。")
        else:
            note = f"本次还没用到在练的词（{'、'.join(targets[:4])}），下次开口造句练一练吧。"
        return {"focus_source": source, "focus_review": note,
                "focus_used": used, "focus_missed": missed}

    label = "、".join(targets[:3])
    note = f"本次围绕「{label}」做了口语练习，多开口、多纠错会更扎实。"
    return {"focus_source": source, "focus_review": note, "focus_used": [], "focus_missed": []}


async def summarize(
    db: AsyncSession, *, student_id, scenario_key: str, history: list[dict],
    stage: str = "junior",
) -> dict:
    """对话结束后给本次练习评价：评分 + 亮点 + 改进 + 鼓励 + 专项掌握点评。"""
    sc = await resolve_scenario(db, student_id=student_id, key=scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    user_turns = [(m.get("text") or "").strip() for m in (history or []) if m.get("role") == "user"]
    user_turns = [t for t in user_turns if t]
    if not user_turns:
        raise ValueError("no user turns")

    focus = _focus_review(sc, user_turns)

    if is_llm_dev_mode():
        return {**_mock_summary(user_turns), **focus}

    level = _LEVEL_BY_STAGE.get(stage, _LEVEL_BY_STAGE["junior"])
    sys = (
        f"You are a kind English speaking coach for a Chinese student at {level} level. "
        f"Based on the student's spoken lines in a roleplay, rate their performance and give "
        f"encouraging, specific feedback. Respond ONLY as compact JSON with keys: "
        f"overall (0-100 int), fluency (0-100), grammar (0-100), vocabulary (0-100), "
        f"highlights (1-3 short Chinese bullet strings on what they did well), "
        f"improvements (1-3 short Chinese bullet strings on what to improve), "
        f"encouragement (one short Chinese sentence)."
    )
    lines = "\n".join(f"- {t}" for t in user_turns[-12:])
    usr = f"Scenario: {sc['title']}.\nStudent's spoken lines:\n{lines}\n\nGive the JSON evaluation now."
    try:
        resp = await chat_completion(
            system_prompt=sys, user_prompt=usr, max_tokens=400,
            response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:  # noqa: BLE001
        logger.warning("[Speaking] 总结 LLM 失败，回退 mock: %s", e)
        return {**_mock_summary(user_turns), **focus}

    def _strlist(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:3]
        return [str(v).strip()] if v else []

    return {
        "overall": _clamp_score(data.get("overall")),
        "fluency": _clamp_score(data.get("fluency")),
        "grammar": _clamp_score(data.get("grammar")),
        "vocabulary": _clamp_score(data.get("vocabulary")),
        "highlights": _strlist(data.get("highlights")) or ["完成了多轮英语对话"],
        "improvements": _strlist(data.get("improvements")) or ["多用完整句子表达"],
        "encouragement": (data.get("encouragement") or "继续加油！").strip(),
        **focus,
    }


async def record_session(
    db: AsyncSession, *, student_id, scenario_key: str, summary: dict, turns: int,
) -> dict:
    """持久化一次口语练习 + 计入今日打卡。返回打卡状态。"""
    import uuid as _uuid
    from app.models.d5_learning import SpeakingSession
    from app.services import checkin_service
    db.add(SpeakingSession(
        id=_uuid.uuid4(), student_id=student_id, scenario_key=scenario_key,
        source=(summary.get("focus_source") or "通用"),
        score=int(summary.get("overall") or 0),
        turns=int(turns or 0),
        used_count=len(summary.get("focus_used") or []),
        missed_count=len(summary.get("focus_missed") or []),
    ))
    await db.flush()
    return await checkin_service.record_study_day(db, student_id=student_id)


async def speaking_stats(db: AsyncSession, student_id) -> dict:
    """口语维度学情：累计/本周练习数、均分、最近分、连续口语天数。"""
    from datetime import datetime, timedelta, timezone, date as _date
    from sqlalchemy import func
    from app.models.d5_learning import SpeakingSession
    rows = (await db.execute(
        select(SpeakingSession.score, SpeakingSession.created_at)
        .where(SpeakingSession.student_id == student_id)
        .order_by(SpeakingSession.created_at.desc())
    )).all()
    total = len(rows)
    if total == 0:
        return {"total_sessions": 0, "week_sessions": 0, "avg_score": 0,
                "last_score": 0, "speaking_streak": 0, "last_practiced_at": None}
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    week = sum(1 for _, c in rows if c and c >= week_ago)
    scores = [s for s, _ in rows if s is not None]
    avg = round(sum(scores) / len(scores)) if scores else 0
    # 连续口语天数（以今天/最近一次结尾）
    days = {c.date() for _, c in rows if c}
    streak = 0
    cur = now.date()
    if cur not in days:
        cur = max(days)
    while cur in days:
        streak += 1
        cur = cur - timedelta(days=1)
    return {
        "total_sessions": total,
        "week_sessions": week,
        "avg_score": avg,
        "last_score": int(rows[0][0] or 0),
        "speaking_streak": streak,
        "last_practiced_at": rows[0][1].isoformat() if rows[0][1] else None,
    }
