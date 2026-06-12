"""AI 口语对话练习 service。

学生用微信同声传译插件做语音识别（或直接打字）→ 文本发到后端，
后端用 LLM 生成自然、难度适配的英文回复 + 轻量纠错，并用火山 TTS（按场景固定
男/女音色）合成回复语音，返回 COS 直链供小程序即点即播。

dev-mock：LLM 占位时走本地确定性回复，整条链路（含 H5 文本路径）可跑通。
"""
from __future__ import annotations

import json
import logging

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
        {"key": s["key"], "title": s["title"], "emoji": s["emoji"], "opening": s["opening"]}
        for s in _SCENARIOS
    ]


def get_scenario(key: str) -> dict | None:
    return _BY_KEY.get(key)


async def opening(db: AsyncSession, *, scenario_key: str, stage: str = "junior") -> dict:
    sc = get_scenario(scenario_key)
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
    db: AsyncSession, *, scenario_key: str, history: list[dict], user_text: str,
    stage: str = "junior",
) -> dict:
    sc = get_scenario(scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    user_text = (user_text or "").strip()[:500]

    if is_llm_dev_mode():
        data = _mock_reply(user_text)
    else:
        level = _LEVEL_BY_STAGE.get(stage, _LEVEL_BY_STAGE["junior"])
        sys = (
            f"You are {sc['persona']}. Have a natural spoken-English conversation with a "
            f"Chinese student at {level} level. Rules: keep your reply to 1-2 SHORT sentences; "
            f"stay in character and on the scenario topic; if the student made a clear English "
            f"mistake, give a brief friendly correction; always end by inviting them to keep "
            f"talking. Respond ONLY as compact JSON with keys: reply (your English line), "
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


async def summarize(
    db: AsyncSession, *, scenario_key: str, history: list[dict], stage: str = "junior",
) -> dict:
    """对话结束后给本次练习评价：评分 + 亮点 + 改进 + 鼓励。"""
    sc = get_scenario(scenario_key)
    if sc is None:
        raise ValueError("scenario not found")
    user_turns = [(m.get("text") or "").strip() for m in (history or []) if m.get("role") == "user"]
    user_turns = [t for t in user_turns if t]
    if not user_turns:
        raise ValueError("no user turns")

    if is_llm_dev_mode():
        return _mock_summary(user_turns)

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
    }
