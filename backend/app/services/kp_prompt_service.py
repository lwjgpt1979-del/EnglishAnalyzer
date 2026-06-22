"""知识点 AI 建议提示词配置(按题型,多套可选默认)。存 system_configs.kp_suggest_prompts。

每条提示词 = {id, name, text(=system 提示), question_type, is_default}。
缺省返回每个题型一条内置默认。供 kp_suggest_service 按题型取 system 提示。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig

_KEY = "kp_suggest_prompts"
QUESTION_TYPES = ["单选", "听力", "填空", "短文填空", "完型", "单词检测", "句子翻译", "阅读", "写作", "其他"]
# 教材来源按板块分别配提示词(短文→考点用「教材·{kind}」;其余正文/语法/词汇用「教材·其他」)。
SOURCE_TYPES = ["教材·听力", "教材·阅读", "教材·写作", "教材·其他"]
ALL_TYPES = QUESTION_TYPES + SOURCE_TYPES

# 内置默认提示词:仅"该题型怎么挑"的指引(放 user 端);
# 角色、知识点目录、输出 JSON 格式由 kp_suggest_service 的稳定 system 前缀统一给出。
_BUILTIN: dict[str, str] = {
    "单选": "【本大题:单项填空 / 语法选择】主要考语法与词汇辨析。为每道小题挑 1-2 个最贴切的"
            "语法或词汇考点(如时态、介词、从句、词义辨析等)。",
    "听力": "【本大题:听力】听力题主要考听力理解能力。若某小题的题干/选项**明确考查某个语法点"
            "或词汇辨析**(如时态、介词、固定搭配、词义辨析),就挑 1 个最贴切的考点;纯听信息/"
            "听大意、不涉及具体语言点的题给空数组。",
    "填空": "【本大题:单词拼写 / 选词填空 / 完成句子】考词汇运用与基础语法。为每题挑 1-2 个"
            "最贴切的词汇或语法考点。",
    "短文填空": "【本大题:短文填空 / 短文语境填词】在短文语境中填词或补全。每空考词汇运用、固定搭配、"
            "语法形式(时态/词形/连词)。请结合上下文,为每空挑 1-2 个最贴切的词汇或语法考点。",
    "完型": "【本大题:完形填空】每空考查一个词汇/语法/语境点。请结合短文语境,为每空挑 1-2 个"
            "最贴切的考点(动词词义、固定搭配、连词、时态等)。",
    "单词检测": "【本大题:单词检测 / 词汇检测】主要考单词拼写与词义。为每题挑 1 个最贴切的词汇考点"
            "(词义辨析、拼写、词形变化等);纯拼写默写、无明确语言点的给空数组。",
    "句子翻译": "【本大题:句子翻译】考词汇与句法结构的综合运用。为每题挑 1-2 个最贴切的语法/句型"
            "或词汇考点(如时态、固定句型、固定搭配、从句结构等)。",
    "阅读": "【本大题:阅读理解 / 信息还原 / 阅读表达】主要考阅读理解能力。若某小题**明确考查某个"
            "词义辨析、语法结构或篇章衔接**(指代、连接词、主旨大意),就挑 1 个最贴切的考点;纯信息"
            "检索/细节定位/逻辑推断、不涉及具体语言点的题给空数组。",
    "写作": "【本大题:书面表达】综合性写作,一般不对应单一语言考点。codes 一律给空数组,"
            "除非题干明确限定考查某语法点。",
    "其他": "【本大题:其他/未归类题型】请判断该题是否明确考查某个语法点或词汇,"
            "若有就挑 1-2 个最贴切的考点;不涉及具体语言点的题给空数组,不要硬凑。",
    "教材·听力": "下面是一篇教材听力短文/对话脚本。请从受控考点目录里挑出它**最适合标注/训练**的"
            "听力考点(可多个),只用目录内编码。",
    "教材·阅读": "下面是一篇教材阅读短文。请从受控考点目录里挑出它**最适合标注/训练**的"
            "阅读考点(可多个),只用目录内编码。",
    "教材·写作": "下面是一段教材写作材料(题目要求/范文)。请从受控考点目录里挑出它**最适合标注/训练**的"
            "写作考点(可多个),只用目录内编码。",
    "教材·其他": "下面是一段教材正文(语法讲解/词汇/课文等其他板块)。请从受控考点目录里挑出这段教材"
            "覆盖/讲解到的考点(可多个),只用目录内编码。",
}


# 每题挑考点的数量范围(至少, 至多)默认
_RANGE: dict[str, tuple[int, int]] = {
    "单选": (1, 2), "听力": (0, 1), "填空": (1, 2), "短文填空": (1, 2), "完型": (1, 2),
    "单词检测": (1, 1), "句子翻译": (1, 2), "阅读": (0, 1), "写作": (0, 1), "其他": (0, 2),
    "教材·听力": (1, 3), "教材·阅读": (1, 3), "教材·写作": (1, 3), "教材·其他": (1, 8),
}


def _builtin_list() -> list[dict]:
    return [{"id": f"builtin-{t}", "name": "内置默认", "text": _BUILTIN[t],
             "question_type": t, "is_default": True, "focus_node_ids": [],
             "min_kp": _RANGE.get(t, (0, 2))[0], "max_kp": _RANGE.get(t, (0, 2))[1]}
            for t in ALL_TYPES]


async def get_prompts(db: AsyncSession) -> list[dict]:
    """读全部提示词;缺失返回内置默认(每题型一条)。"""
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None or not isinstance(cfg.value, dict) or not cfg.value.get("prompts"):
        return _builtin_list()
    stored = cfg.value["prompts"]
    # 旧配置里的单一「教材」→ 归到新的「教材·其他」板块(向后兼容)
    for p in stored:
        if p.get("question_type") == "教材":
            p["question_type"] = "教材·其他"
    # 缺失的板块补内置默认,保证 4 个教材板块都有(及题型)。
    have = {p.get("question_type") for p in stored}
    for t in ALL_TYPES:
        if t not in have:
            stored.append(next(b for b in _builtin_list() if b["question_type"] == t))
    return stored


async def save_prompts(db: AsyncSession, *, prompts: list[dict], updated_by: uuid.UUID) -> list[dict]:
    """保存提示词(整体覆盖)。每题型至多一个 is_default;补 id。"""
    cleaned: list[dict] = []
    seen_default: set[str] = set()
    for p in prompts:
        qt = p.get("question_type")
        if qt not in ALL_TYPES or not (p.get("text") or "").strip():
            continue
        is_def = bool(p.get("is_default")) and qt not in seen_default
        if is_def:
            seen_default.add(qt)
        mn = max(0, min(10, int(p.get("min_kp") or 0)))
        mx = max(1, min(10, int(p.get("max_kp") or 2)))
        if mn > mx:
            mn = mx
        cleaned.append({
            "id": p.get("id") or f"p-{uuid.uuid4().hex[:8]}",
            "name": (p.get("name") or "未命名").strip(),
            "text": p["text"].strip(), "question_type": qt, "is_default": is_def,
            "focus_node_ids": [str(x) for x in (p.get("focus_node_ids") or [])],
            "min_kp": mn, "max_kp": mx,
        })
    # 每题型若无默认,把该型第一个置默认
    for t in ALL_TYPES:
        group = [p for p in cleaned if p["question_type"] == t]
        if group and not any(p["is_default"] for p in group):
            group[0]["is_default"] = True
    value = {"prompts": cleaned}
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=value,
                            description="知识点 AI 建议提示词(按题型)", updated_by=updated_by))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    await db.flush()
    return cleaned


def default_item_for(prompts: list[dict], qtype: str | None) -> dict:
    """取某题型的默认提示词条目(text + focus_node_ids);无配置回内置。"""
    qt = qtype or "单选"
    for p in prompts:
        if p["question_type"] == qt and p.get("is_default"):
            return p
    for p in prompts:
        if p["question_type"] == qt:
            return p
    rng = _RANGE.get(qt, (0, 2))
    return {"text": _BUILTIN.get(qt, _BUILTIN["单选"]), "focus_node_ids": [],
            "min_kp": rng[0], "max_kp": rng[1]}


def item_by_id(prompts: list[dict], prompt_id: str | None) -> dict | None:
    for p in prompts:
        if p["id"] == prompt_id:
            return p
    return None
