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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


def list_scenarios() -> list[dict]:
    return [
        {"key": s["key"], "title": s["title"], "emoji": s["emoji"],
         "opening": s["opening"], "tag": "preset"}
        for s in _SCENARIOS
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
    """因材施教的个性化场景：学期内容 + 词力通在练 + 错题薄弱点。"""
    out: list[dict] = []
    out.extend(await _semester_units(db, student_id))
    words = await _vocab_words(db, student_id)
    if len(words) >= 3:
        out.append({
            "key": "vocab", "title": "词力通在练词", "emoji": "🔤",
            "opening": f"Time to use your new words! Can you make a sentence with \"{words[0]}\"?",
            "tag": "custom", "source": "词力通",
        })
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
    preset = get_scenario(key)
    if preset is not None:
        return {**preset, "focus": ""}

    g = _gender_for_key(key)
    if key.startswith("sem:"):
        import uuid as _uuid
        try:
            unit_id = str(_uuid.UUID(key[4:]))
        except (ValueError, AttributeError):
            return None
        from app.models.d4_knowledge import CurriculumUnit
        row = (await db.execute(
            select(CurriculumUnit.unit_title).where(CurriculumUnit.id == unit_id)
        )).first()
        if row is None:
            return None
        title = row[0] or "this unit"
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
        sys = (
            f"You are {sc['persona']}. Have a natural spoken-English conversation with a "
            f"Chinese student at {level} level. Rules: keep your reply to 1-2 SHORT sentences; "
            f"stay in character and on the scenario topic; if the student made a clear English "
            f"mistake, give a brief friendly correction; always end by inviting them to keep "
            f"talking. " + (f"Personalization: {focus} " if focus else "")
            + "Respond ONLY as compact JSON with keys: reply (your English line), "
            f"correction (a short note on the student's mistake, or empty string), "
            f"translation (a Chinese translation of your reply)."
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
        return _mock_summary(user_turns)

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
