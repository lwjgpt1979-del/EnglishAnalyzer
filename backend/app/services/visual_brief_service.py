"""表意配图·唯一强制入口:把「要表意的词/考点/例句」→ 分类 + 一句可画场景 + 出图决策。

全项目铁律:凡「为表意生成图像」一律经 plan_visual —— 不允许各处内嵌 brief/闸门。
三层里的 L1(路由)+ L2(造场景);L3 质量复核仍在 doubao_vision_service。

结局(outcome):
- draw       : 有可画场景 → 交调用方出图(下游 t2i + 复核)。
- text_only  : 纯语法虚词(a/an/the/of…)本就画不出义 → 无图词义卡,别再重试(决策 B)。
- retry      : 本次造场景失败(LLM 空/异常)→ 暂时无图,下次「查看即生成」再试。

决策(已定):
① 不预判抽象词不可画 —— think/happy/because/freedom/空间介词 都造具体场景出图;
   drawable 按「场景」可画性打分(通常 >=0.7),不再按裸词自评低分拒。
② 无图只发生在:纯语法虚词(text_only)或造场景失败(retry)或下游复核降级(调用方判)。
"""
from __future__ import annotations

from app.services import llm_provider

# L1+L2 元指令(默认;后台「配图-画面描述指令」可覆盖,经 system= 传入)。P0 已验证出图合理。
DEFAULT_BRIEF_SYSTEM = (
    "You turn an English word into ONE concrete scene a text-to-image model can draw so a learner "
    "instantly grasps the word's MEANING. Route by the word:\n"
    "- Concrete object or action (apple, run): depict it directly.\n"
    "- Feeling or mental state (happy, worry, think, decide): depict a PERSON whose facial expression "
    "and posture clearly convey it; a thought bubble is allowed.\n"
    "- Word with a well-known visual metaphor (freedom, time): use that metaphor.\n"
    "- Other abstract word, or a SPATIAL preposition (in, on, under, between): depict the scene of ONE "
    "simple concrete example sentence that uses the word (a cat sits in a box).\n"
    "- PURELY grammatical word whose meaning is only structural — articles (a, an, the) and non-spatial "
    "grammatical particles (of, the infinitive 'to'): a picture cannot teach these; do NOT invent a scene.\n"
    "Describe ONLY what is visible, specific to this meaning. Show a person only when the meaning is a "
    "person/feeling/human action; otherwise show only the thing. No text or numbers in the image, no style words."
)
_JSON_HINT = (
    ' Return ONLY a JSON object: {"category": "concrete|emotion|mental|metaphor|abstract|spatial|function_grammatical",'
    ' "scene": "<one visible-only English sentence; EMPTY string only if function_grammatical>",'
    ' "drawable": <0.0-1.0 = how depictable YOUR scene is; since you produced a concrete scene this is usually >=0.7;'
    ' 0 for function_grammatical>}.'
)


async def plan_visual(term: str, meaning: str, *, pos: str = "", kind: str = "word",
                      en_desc: str = "", all_defs: str = "", system: str | None = None) -> dict:
    """把 term 转成 {category, scene, drawable, outcome, reason}。
    kind:表意对象类型(word/kp/example…),供未来按类型微调,当前统一策略。
    dev-mock → 直接可画(走原模板)。"""
    if llm_provider.is_llm_dev_mode():
        return {"category": "concrete", "scene": "", "drawable": 1.0,
                "outcome": "draw", "reason": ""}
    sysp = (system or DEFAULT_BRIEF_SYSTEM) + _JSON_HINT
    up = (f"Word/phrase: {term}\nPart of speech: {pos}\nMeaning (Chinese): {meaning}"
          + (f"\nEnglish gloss: {en_desc}" if en_desc else "")
          + (f"\nAll senses: {all_defs}" if all_defs else ""))
    for _ in range(2):
        try:
            data = await llm_provider.complete_json(
                system_prompt=sysp, user_prompt=up, max_tokens=320,
                model=llm_provider.fast_model(), feature="vocab_image_brief",
                disable_thinking=True)
            if not data:
                continue
            category = str(data.get("category") or "").strip()
            scene = str(data.get("scene") or "").strip().replace("\n", " ")
            try:
                drawable = max(0.0, min(1.0, float(data.get("drawable", 0.7))))
            except (TypeError, ValueError):
                drawable = 0.7
            if category == "function_grammatical":       # 决策B:纯语法虚词 → 无图词义卡,不重试
                return {"category": category, "scene": "", "drawable": 0.0,
                        "outcome": "text_only", "reason": "纯语法虚词,图教不了语法义"}
            if len(scene) >= 12:                          # 有合格场景 → 出图
                return {"category": category or "abstract", "scene": scene, "drawable": drawable,
                        "outcome": "draw", "reason": ""}
            # 场景太短/空但又非纯虚词 → 本次失败,重试
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("[plan_visual] %s 失败: %s", term, e)
    return {"category": "", "scene": "", "drawable": 0.0,
            "outcome": "retry", "reason": "造场景失败(LLM 空/异常),下次重试"}
