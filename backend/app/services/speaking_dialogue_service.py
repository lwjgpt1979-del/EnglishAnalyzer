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
    "You are an exam-mistake review coach. You quiz the student on a question they got "
    "wrong, check their answer, and—when they are wrong—explain the reason clearly and "
    "kindly, including what the distractor options are testing. Stay patient and focused.")
_DEF_VOCAB_PROMPT = (
    "You are a vocabulary listening and pronunciation coach. You help the student hear, "
    "say, and use their words, and you gently correct mispronunciations with simple tips.")
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


def _vocab_focus(words: list[str]) -> str:
    return (
        "This is a VOCABULARY LEARNING chat. The APP shows each target word to the student as a card "
        "(word + phonetic + picture) and plays its audio — so do NOT introduce, name, spell out, or quote "
        "any specific next word yourself, and do NOT say things like \"listen again: 'xxx'\". "
        "Instead, in 1-2 short sentences: warmly react to what the student just said (praise + a gentle "
        "correction or pronunciation tip if needed), then invite them to look at and read the next word "
        "card aloud (e.g. \"Nice! Now look at the next word and read it out loud.\"). Keep it short and "
        "encouraging."
    )


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


async def vocab_cards(db: AsyncSession, student_id, *, limit: int = 12) -> list[dict]:
    """词力通在练词的词卡：单词 + 英标 + 释义 + 图片 + 发音音频(无则前端用TTS兜底)。"""
    from app.models.d5_learning import VocabularyLearning, VocabularyWord
    rows = (await db.execute(
        select(VocabularyWord.word, VocabularyWord.phonetic, VocabularyWord.definitions,
               VocabularyWord.image_urls, VocabularyWord.word_audio_url,
               VocabularyWord.examples, VocabularyWord.phrases)
        .join(VocabularyLearning, VocabularyLearning.word_id == VocabularyWord.id)
        .where(VocabularyLearning.student_id == student_id)
        .order_by(VocabularyLearning.next_review_at.asc()).limit(limit)
    )).all()

    def _first(jl):
        if isinstance(jl, list) and jl and isinstance(jl[0], dict):
            return {"en": str(jl[0].get("en", "")), "zh": str(jl[0].get("zh", "")),
                    "audio": str(jl[0].get("audio", ""))}
        return None

    out: list[dict] = []
    for word, phon, defs, imgs, audio, examples, phrases in rows:
        meaning = ""
        if isinstance(defs, list) and defs and isinstance(defs[0], dict):
            meaning = str(defs[0].get("meaning") or "")
        out.append({
            "word": word, "phonetic": phon or "",
            "meaning": meaning[:40],
            "image_urls": ([str(u) for u in imgs][:2] if isinstance(imgs, list) else []),
            "audio_url": audio or "",
            "example": _first(examples),
            "phrase": _first(phrases),
        })
    return out


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


async def _wq_kp_names(db: AsyncSession, wq_id, *, limit: int = 4) -> list[str]:
    from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
    rows = (await db.execute(
        select(KnowledgePoint.name)
        .join(WrongQuestionKnowledgePoint,
              WrongQuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .where(WrongQuestionKnowledgePoint.wrong_question_id == wq_id).limit(limit)
    )).all()
    return [r[0] for r in rows if r[0]]


async def _top_wrong_from_record(db: AsyncSession, student_id) -> dict | None:
    """R7:优先从 KP-First 错题中心 wrong_record(open, uploaded)取一道,join uploaded_question 取内容。"""
    from app.models.d16_question_domain import WrongRecord, UploadedQuestion
    from app.models.d15_knowledge_graph import KnowledgeNode
    row = (await db.execute(
        select(WrongRecord, UploadedQuestion)
        .join(UploadedQuestion, UploadedQuestion.id == WrongRecord.question_id)
        .where(WrongRecord.student_id == student_id, WrongRecord.status == "open",
               WrongRecord.q_scope == "uploaded")
        .order_by(WrongRecord.next_review_at.asc().nullsfirst(), WrongRecord.created_at.asc())
        .limit(1)
    )).first()
    if row is None:
        return None
    wr, uq = row
    kps = []
    if wr.node_id is not None:
        nm = (await db.execute(
            select(KnowledgeNode.name).where(KnowledgeNode.id == wr.node_id))).scalar_one_or_none()
        if nm:
            kps = [nm]
    return {
        "id": str(wr.id),
        "stem": (uq.stem or "").strip()[:300],
        "answer": (uq.correct_answer or "").strip()[:200],
        "student_answer": (uq.student_answer or "").strip()[:200],
        "kps": kps,
    }


async def _top_due_wrong(db: AsyncSession, student_id) -> dict | None:
    """取最该复习的一道错题（KP-First 中心优先，回退旧错题本），含题干/正确答案/知识点。"""
    from datetime import date as _date
    from app.models.d3_wrong_questions import WrongQuestion
    # R7:口语错题复习先读 wrong_record 中心(有内容则用),否则回退旧 WrongQuestion
    from_center = await _top_wrong_from_record(db, student_id)
    if from_center is not None:
        return from_center
    today = _date.today()
    wq = (await db.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == student_id, WrongQuestion.is_mastered.is_(False),
            WrongQuestion.next_review_at.is_not(None), WrongQuestion.next_review_at <= today,
        ).order_by(WrongQuestion.next_review_at.asc()).limit(1)
    )).scalar_one_or_none()
    if wq is None:
        wq = (await db.execute(
            select(WrongQuestion).where(
                WrongQuestion.student_id == student_id, WrongQuestion.is_mastered.is_(False),
                WrongQuestion.next_review_at.is_(None),
            ).order_by(WrongQuestion.created_at.asc()).limit(1)
        )).scalar_one_or_none()
    if wq is None:
        return None
    return {
        "id": str(wq.id),
        "stem": (wq.question_text or "").strip()[:300],
        "answer": (wq.correct_answer or "").strip()[:200],
        "student_answer": (wq.student_answer or "").strip()[:200],
        "kps": await _wq_kp_names(db, wq.id),
    }


async def _due_wrong_count(db: AsyncSession, student_id) -> int:
    from app.services import review_service
    stats = await review_service.get_review_stats(db, student_id=student_id)
    return int(stats.get("due_today", 0)) + int(stats.get("new_unscheduled", 0))


async def _credit_vocab_usage(
    db: AsyncSession, student_id, *, targets: list[str], user_text: str, history: list[dict],
) -> list[dict]:
    """词力通：学生本轮新用对的目标词 → 各记一次 SM-2 正确，推进熟练度。

    只给「本轮出现且此前对话未出现过」的词记分，避免同词刷分。返回 [{word, level}]。
    """
    targets = [t for t in (targets or []) if t]
    if not targets:
        return []
    now_low = (user_text or "").lower()
    prev_low = " ".join(
        (m.get("text") or "") for m in (history or []) if m.get("role") == "user"
    ).lower()
    newly = [w for w in targets if w.lower() in now_low and w.lower() not in prev_low]
    if not newly:
        return []

    from sqlalchemy import func
    from app.models.d5_learning import VocabularyWord
    from app.services import vocabulary_service
    out: list[dict] = []
    for w in newly[:4]:
        wid = (await db.execute(
            select(VocabularyWord.id).where(func.lower(VocabularyWord.word) == w.lower()).limit(1)
        )).scalar_one_or_none()
        if wid is None:
            continue
        try:
            res = await vocabulary_service.submit_answer(
                db, student_id=student_id, word_id=wid, correct=True)
            out.append({"word": w, "level": str(res.level)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[Speaking] 词力通记分失败 %s: %s", w, e)
    return out


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
        due = await _due_wrong_count(db, student_id)
        if due > 0:
            out.append({
                "key": "wrong", "title": f"错题复习（待复习 {due}）", "emoji": "🎯",
                "opening": "Let's review a question you got wrong, step by step. Ready?",
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
        focus = _vocab_focus(words)
        return {
            "key": key, "title": "专项练词", "emoji": "🔤", "gender": g,
            "persona": "a vocabulary listening & pronunciation coach",
            "opening": f"Let's practice saying these words: {', '.join(words)}. "
                       f"Listen, then say \"{words[0]}\" out loud and use it in a short sentence.",
            "focus": focus, "source": "词力通", "targets": words, "target_kind": "word",
            "prompt": cfg["special"]["vocab"]["prompt"],
        }

    if key == "vocab":
        words = await _vocab_words(db, student_id)
        if not words:
            return None
        focus = _vocab_focus(words)
        return {
            "key": "vocab", "title": "词力通在练词", "emoji": "🔤", "gender": g,
            "persona": "a vocabulary listening & pronunciation coach",
            "opening": f"Let's practice your words by listening and speaking! "
                       f"Say \"{words[0]}\" out loud and use it in a short sentence.",
            "focus": focus, "source": "词力通", "targets": words, "target_kind": "word",
            "prompt": cfg["special"]["vocab"]["prompt"],
        }

    if key == "wrong":
        wq = await _top_due_wrong(db, student_id)
        if wq is None:
            return None
        kp_str = "、".join(wq["kps"]) or "this language point"
        focus = (
            f"This is an EXAM-MISTAKE REVIEW for ONE specific question the student got wrong. "
            f"Knowledge point: {kp_str}. "
            f"The question (with its options if any): \"{wq['stem']}\". "
            f"Correct answer: \"{wq['answer']}\". "
            + (f"The student previously chose the WRONG answer: \"{wq['student_answer']}\". "
               if wq['student_answer'] else "")
            + "Procedure: (1) Read the question to the student and ask them to answer it (do NOT reveal "
            "the answer). (2) Check their answer. If CORRECT: affirm warmly in one line and set "
            "\"mastered\": true (we will move to the next question). If WRONG: keep \"mastered\": false, "
            "explain clearly WHY their answer is wrong, and briefly explain what the distractor option(s) "
            "are testing and why they are traps; then ask them to try again. Stay on THIS question until "
            "they answer it correctly."
        )
        return {
            "key": "wrong", "title": "错题复习", "emoji": "🎯", "gender": g,
            "persona": "an exam-mistake review coach who quizzes the student and explains errors",
            "opening": (f"Let's review a question you got wrong, about {kp_str}. Here it is: "
                        f"{wq['stem'][:180]} ... What's your answer?")
                       if wq['stem'] else
                       f"Let's review a question you got wrong about {kp_str}. Ready to try it again?",
            "focus": focus, "source": "错题薄弱点", "targets": wq["kps"] or [kp_str],
            "target_kind": "point", "prompt": cfg["special"]["wrong"]["prompt"],
            "wrong_question_id": wq["id"],
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
        # 词力通等练词场景：返回目标词，供前端「测发音」逐词调 SOE 评测
        "target_words": (sc.get("targets") or []) if sc.get("target_kind") == "word" else [],
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


def _speakable(text: str) -> str:
    """清洗点评文本以便 TTS：去掉国际音标(/.../ 与 IPA 字符)，避免火山 TTS 'unsupported language'。"""
    import re
    t = re.sub(r"/[^/\n]{0,24}/", "", text or "")          # 去掉 /ð/、/aɪ/ 等音标段
    t = re.sub(r"[ɐ-ʯæðθʃʒŋː]", "", t)  # 残留 IPA 字符
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t


def _mock_coach(user_text: str, pron: dict | None) -> dict:
    weak = ""
    if pron and isinstance(pron.get("words"), list):
        weak = "、".join(w["word"] for w in pron["words"] if w.get("score", 100) < 80)
    return {
        "encourage": "说得不错，开口很清楚！👏",
        "pron_tip": (f"有几个词再练练：{weak}，跟我慢慢读一遍。" if weak
                     else "发音清楚，继续保持。"),
        "express_tip": "可以试着把句子说得更完整一点，比如加上主语和动词。",
        "better": user_text,
    }


async def _mom_coach(user_text: str, pron: dict | None, *, focus: str = "",
                     target_text: str = "") -> dict:
    """像妈妈教小朋友那样做温柔的互动式点评：鼓励 + 发音提点 + 建议。

    target_text 非空（词力通朗读）→ 评测针对的是孩子朗读这句「目标原文」，
    点评须围绕目标原文里读得不准的词，示范说法用目标原文本身。
    """
    if is_llm_dev_mode():
        return _mock_coach(target_text or user_text, pron)
    weak_words, scores = "", ""
    if pron:
        if isinstance(pron.get("words"), list):
            weak_words = "、".join(w["word"] for w in pron["words"] if w.get("score", 100) < 80)
        scores = (f"发音总分{pron.get('overall')}, 准确度{pron.get('accuracy')}, "
                  f"流利度{pron.get('fluency')}, 完整度{pron.get('completion')}. "
                  f"读得不够准的词：{weak_words or '无'}.")
    try:
        if target_text:
            system_prompt = (
                "你在帮助一个正在【反复练习朗读同一句指定英文】的学习者，目标是把这句话读准。"
                "请用中文点评，且【只针对这句目标原文】，不要分析语音识别里的杂词。"
                "要求：(1) encourage 只用一句很简短的肯定（不要长篇套话）。"
                "(2) pron_tip 是重点：结合发音评测，点名目标原文里读得最不准的 1-2 个单词，"
                "具体讲这个音的口型/舌位/气流怎么做，让对方能照着改。"
                "【不要使用国际音标符号（如 /ð/、/æ/、/aɪ/、ː 等）】，"
                "改用字母或中文把发音说清楚（例如：th 音、v 音、把 ee 音拉长），方便念出来听。"
                "(3) express_tip 用一句话提示【跟着范本再读一遍】这同一句话，把刚才的音读对。"
                "(4) 绝对不要提到‘下一个词/下一张卡/next word/next card/换下一个’——换词由对方自己决定，"
                "只负责把当前这句反复带读到读准。"
                "【非常重要】输出文本里不要出现任何称呼或自称（如 妈妈、老师、宝贝、亲爱的、同学、孩子、你呀 等），"
                "直接讲发音要点；需要示意一起读时最多说‘跟我读’。语气平和、简洁，每条一两句。"
                "只输出紧凑 JSON，键为：encourage(一句简短肯定), pron_tip(针对具体单词的发音纠正+口型舌位), "
                "express_tip(提示再读一遍的话), better(就是这句目标原文本身, 作为跟读范本, 英文)。"
                + (f" 本活动目标：{focus}。" if focus else "")
            )
            user_prompt = (f"目标原文（孩子在反复朗读的句子/短语）：{target_text}\n"
                           f"语音识别到的内容（仅供参考，可能不准）：{user_text}\n"
                           f"{('发音评测（针对目标原文）：' + scores) if scores else '（本句暂无发音评测数据）'}\n"
                           f"请只围绕目标原文，带孩子把这句读准；不要提下一个词。")
        else:
            system_prompt = (
                "你在帮助一个学习者练习说英语。请用中文做互动式点评：先简短肯定具体做得好的地方，"
                "再指出 1 个最值得改进的发音点（结合给出的发音评测，点名具体单词，说清这个音怎么读准），"
                "最后给 1 条让表达更自然/更完整的小建议，并示范一句更地道的说法。"
                "【非常重要】输出文本里不要出现任何称呼或自称（如 妈妈、老师、宝贝、亲爱的、同学、孩子 等），"
                "直接讲要点；需要示意一起读时最多说‘跟我读’。语气平和、简洁，不要长篇大论，每条一两句。"
                "只输出紧凑 JSON，键为："
                "encourage(肯定), pron_tip(发音提点), express_tip(表达建议), better(示范的更好说法, 英文)。"
                + (f" 本活动目标：{focus}。" if focus else "")
            )
            user_prompt = (f"孩子说的英文：{user_text}\n"
                           f"{('发音评测：' + scores) if scores else '（本句暂无发音评测数据）'}\n"
                           f"请按要求点评。")
        resp = await chat_completion(
            system_prompt=system_prompt, user_prompt=user_prompt,
            max_tokens=320, response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {
            "encourage": (data.get("encourage") or "").strip(),
            "pron_tip": (data.get("pron_tip") or "").strip(),
            "express_tip": (data.get("express_tip") or "").strip(),
            "better": (data.get("better") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("[妈妈陪练] 点评失败，回退 mock: %s", e)
        return _mock_coach(user_text, pron)


async def reply(
    db: AsyncSession, *, student_id, scenario_key: str, history: list[dict], user_text: str,
    stage: str = "junior", audio_b64: str | None = None, audio_format: str = "mp3",
    coach: bool = False, ref_text: str | None = None,
) -> dict:
    sc = await resolve_scenario(db, student_id=student_id, key=scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    user_text = (user_text or "").strip()[:500]

    # 陪练模式：只出发音点评，不再生成对话回复（避免冗余的“看下一张卡”气泡 + 省一次LLM）
    skip_dialogue = coach
    if skip_dialogue:
        data = {}
    elif is_llm_dev_mode():
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
            + "Keep replies concise (about 1-3 short sentences). "
            + "STAY STRICTLY ON THE GOAL OF THIS ACTIVITY: if the student asks something off-topic "
            "or tries to change the subject, answer in ONE short sentence and then immediately steer "
            "back to the task. Do not get pulled away from the activity's purpose. "
            + (f"Task: {focus} " if focus else "")
            + "Respond ONLY as compact JSON with keys: reply (your English line; you may add a brief "
            "Chinese clause when correcting so the student understands), "
            "correction (a short note on the student's mistake, or empty string), "
            "translation (a Chinese translation of your reply), "
            "mastered (boolean, true ONLY when the student just answered correctly / clearly "
            "demonstrated they now understand the reviewed point; otherwise false)."
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

    if skip_dialogue:
        ai_text, audio = "", ""
    else:
        ai_text = (data.get("reply") or "").strip() or "Let's keep practicing! Tell me more."
        speed = await tts_service.speed_for_stage_db(db, stage)
        voice = await tts_service.first_voice(db, sc["gender"])
        audio = await tts_service.get_or_create_audio_url(ai_text, voice=voice, speed=speed)

    # 错题复习：学生答对 → 提交一次成功复习（SM-2），从今日待复习队列中减一
    mastered_wrong = None
    wq_id = sc.get("wrong_question_id")
    if wq_id and bool(data.get("mastered")):
        try:
            import uuid as _uuid
            from app.services import review_service
            await review_service.submit_review(
                db, wq_id=_uuid.UUID(wq_id), student_id=student_id, quality=5)
            due_left = await _due_wrong_count(db, student_id)
            mastered_wrong = {
                "kp": "、".join(sc.get("targets") or []) or "该知识点",
                "due_left": due_left,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[Speaking] 错题复习标记失败: %s", e)

    # 词力通：学生本轮新用对的目标词 → 各推进一次熟练度（SM-2）
    vocab_practiced: list[dict] = []
    if sc.get("target_kind") == "word":
        vocab_practiced = await _credit_vocab_usage(
            db, student_id, targets=sc.get("targets") or [],
            user_text=user_text, history=history)

    # 陪练：对孩子这句英文做音频测评 + 互动式点评（仅 coach 模式开启时）
    # 词力通朗读场景：以词卡「例句/短语」原文(ref_text)为评测参照，而非语音识别文本
    pron = None
    coach_out = None
    if coach:
        target = (ref_text or "").strip()        # 朗读目标原文（有则据此评测/点评）
        pron_ref = target or user_text
        audio_bytes = None
        if audio_b64:
            try:
                import base64 as _b64
                audio_bytes = _b64.b64decode(audio_b64)
            except Exception as e:  # noqa: BLE001
                logger.warning("[陪练] 音频解码失败: %s", e)
        if audio_bytes:
            try:
                from app.services import pronunciation_service
                pron = await pronunciation_service.assess(
                    reference_text=pron_ref, audio_bytes=audio_bytes,
                    mode="sentence", audio_format=(audio_format or "mp3"))
            except Exception as e:  # noqa: BLE001
                logger.warning("[陪练] 发音评测失败: %s", e)
        coach_out = await _mom_coach(user_text, pron, focus=(sc.get("focus") or "").strip(),
                                     target_text=target)
        # 把点评（肯定+发音纠正+再读一遍）合成真人语音，前端自动播放，像老师在旁边讲
        if coach_out:
            spoken = _speakable(" ".join(p for p in [coach_out.get("encourage"),
                                                     coach_out.get("pron_tip"),
                                                     coach_out.get("express_tip")] if p))
            try:
                coach_out["audio"] = (await tts_service.get_or_create_audio_url(
                    spoken, voice=tts_service.zh_voice())) or "" if spoken else ""
            except Exception as e:  # noqa: BLE001
                logger.warning("[陪练] 点评语音合成失败: %s", e)
                coach_out["audio"] = ""

    return {
        "ai_text": ai_text,
        "ai_audio_url": audio or "",
        "correction": (data.get("correction") or "").strip(),
        "translation": (data.get("translation") or "").strip(),
        "mastered_wrong": mastered_wrong,
        "vocab_practiced": vocab_practiced,
        "pron": pron,
        "coach": coach_out,
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


def _vocab_pron_report(pron_log: list[dict] | None) -> dict | None:
    """词力通陪练结束综合报告：从逐句发音评测记录聚合 练词/均分/薄弱音/进步趋势。

    pron_log 每项：{word, overall, accuracy, fluency, completion, weak:[..]}。
    """
    items = [it for it in (pron_log or []) if isinstance(it, dict) and it.get("overall") is not None]
    if not items:
        return None

    def _avg(vals):
        vals = [v for v in vals if v is not None]
        return int(round(sum(vals) / len(vals))) if vals else None

    bars = [int(it["overall"]) for it in items]
    avg = _avg(bars)
    dims = {
        "accuracy": _avg([it.get("accuracy") for it in items]),
        "fluency": _avg([it.get("fluency") for it in items]),
        "completion": _avg([it.get("completion") for it in items]),
    }
    # 练过的词（去重保序）
    words: list[str] = []
    for it in items:
        w = (it.get("word") or "").strip()
        if w and w not in words:
            words.append(w)
    # 最佳一句
    best_it = max(items, key=lambda it: it["overall"])
    best = {"word": (best_it.get("word") or "").strip(), "score": int(best_it["overall"])}
    # 薄弱词：按出现频次排序
    from collections import Counter
    wc: Counter = Counter()
    for it in items:
        for w in (it.get("weak") or []):
            w = str(w).strip()
            if w:
                wc[w] += 1
    weak_words = [w for w, _ in wc.most_common(6)]
    # 进步趋势：后半段均分 vs 前半段
    trend = "flat"
    if len(bars) >= 2:
        mid = len(bars) // 2
        first, second = _avg(bars[:mid]) or 0, _avg(bars[mid:]) or 0
        if second - first >= 5:
            trend = "up"
        elif first - second >= 5:
            trend = "down"
    # 评语（确定性，无需额外 LLM）
    if avg is not None and avg >= 90:
        comment = "发音很标准，整体非常棒！"
    elif avg is not None and avg >= 75:
        comment = "发音整体不错，再打磨几个细节会更好。"
    else:
        comment = "开口很认真，多跟读练习会进步很快。"
    if weak_words:
        comment += f" 重点再练：{'、'.join(weak_words[:4])}。"
    if trend == "up":
        comment += " 而且越读越好，进步很明显 📈"

    return {
        "count": len(items), "words": words, "avg": avg, "best": best,
        "weak_words": weak_words, "dims": dims, "trend": trend,
        "bars": bars[-12:], "comment": comment,
    }


async def summarize(
    db: AsyncSession, *, student_id, scenario_key: str, history: list[dict],
    stage: str = "junior", pron_log: list[dict] | None = None,
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
    vocab_report = _vocab_pron_report(pron_log)

    if is_llm_dev_mode():
        return {**_mock_summary(user_turns), **focus, "vocab_report": vocab_report}

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
        return {**_mock_summary(user_turns), **focus, "vocab_report": vocab_report}

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
        "vocab_report": vocab_report,
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
