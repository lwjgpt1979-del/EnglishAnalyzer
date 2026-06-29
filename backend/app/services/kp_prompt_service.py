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
             "min_kp": _RANGE.get(t, (0, 2))[0], "max_kp": _RANGE.get(t, (0, 2))[1],
             "focus_ranges": {}}
            for t in ALL_TYPES]


def range_for(item: dict, node_id) -> tuple[int, int]:
    """某「关注分类」的考点数范围(至少, 至多)。该分类没单独配 → 回退提示词级 min_kp/max_kp。"""
    r = (item.get("focus_ranges") or {}).get(str(node_id))
    if isinstance(r, (list, tuple)) and len(r) == 2:
        return int(r[0]), int(r[1])
    return int(item.get("min_kp") or 0), int(item.get("max_kp") or 2)


def make_scope(textbook: str | None, grade: str | None, semester: str | None) -> str | None:
    """学期 scope 串(教材版本|年级|学期);任一缺失 → None(用全局默认)。"""
    if textbook and grade and semester:
        return f"{textbook}|{grade}|{semester}"
    return None


def _scoped_key(scope: str | None) -> str:
    return _KEY if not scope else f"{_KEY}::{scope}"


def _normalize(stored: list[dict]) -> list[dict]:
    """补全:旧「教材」→教材·其他、缺 focus_ranges 字段、缺题型/板块补内置默认。"""
    for p in stored:
        if p.get("question_type") == "教材":
            p["question_type"] = "教材·其他"
        p.setdefault("focus_ranges", {})
    have = {p.get("question_type") for p in stored}
    for t in ALL_TYPES:
        if t not in have:
            stored.append(next(b for b in _builtin_list() if b["question_type"] == t))
    return stored


async def _load(db: AsyncSession, key: str) -> list[dict] | None:
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if cfg is None or not isinstance(cfg.value, dict) or not cfg.value.get("prompts"):
        return None
    return _normalize(cfg.value["prompts"])


async def get_prompts(db: AsyncSession, scope: str | None = None) -> list[dict]:
    """读提示词。scope=学期串则优先用该学期定制;无定制 → 回退全局;全局也无 → 内置默认。"""
    if scope:
        scoped = await _load(db, _scoped_key(scope))
        if scoped is not None:
            return scoped
    return (await _load(db, _KEY)) or _builtin_list()


async def _raw_value(db: AsyncSession, key: str) -> dict | None:
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    return cfg.value if (cfg is not None and isinstance(cfg.value, dict)) else None


async def get_passage_include_skill(db: AsyncSession, scope: str | None = None) -> bool:
    """短文板块是否**也匹配「答题技能类」考点**(推理判断/情景反应/信息计算/词义猜测/同义转换)。

    默认 False=排除(短文只挂内容类,当前收紧行为)。按 scope→全局回退;都没配=默认。
    """
    keys = ([_scoped_key(scope)] if scope else []) + [_KEY]
    for key in keys:
        v = await _raw_value(db, key)
        if v is not None and "passage_include_skill" in v:
            return bool(v["passage_include_skill"])
    return False


async def save_prompts(db: AsyncSession, *, prompts: list[dict], updated_by: uuid.UUID,
                       scope: str | None = None,
                       passage_include_skill: bool | None = None) -> list[dict]:
    """保存提示词(整体覆盖)。每题型至多一个 is_default;补 id。scope=学期串则存该学期定制。

    passage_include_skill 非空则一并存「短文是否匹配答题技能类考点」开关;为 None 保留原值。
    """
    cleaned: list[dict] = []
    seen_default: set[str] = set()
    for p in prompts:
        qt = p.get("question_type")
        if qt not in ALL_TYPES or not (p.get("text") or "").strip():
            continue
        is_def = bool(p.get("is_default")) and qt not in seen_default
        if is_def:
            seen_default.add(qt)
        mn = max(0, min(99, int(p.get("min_kp") or 0)))
        mx = max(1, min(99, int(p.get("max_kp") or 2)))
        if mn > mx:
            mn = mx
        fids = [str(x) for x in (p.get("focus_node_ids") or [])]
        # 每个关注分类各自的考点数范围;只保留当前选中分类的、并各自校验夹紧
        fr_in = p.get("focus_ranges") or {}
        focus_ranges: dict[str, list[int]] = {}
        for nid in fids:
            r = fr_in.get(nid)
            if isinstance(r, (list, tuple)) and len(r) == 2:
                cmn = max(0, min(99, int(r[0] or 0)))
                cmx = max(1, min(99, int(r[1] or 1)))
                if cmn > cmx:
                    cmn = cmx
                focus_ranges[nid] = [cmn, cmx]
        cleaned.append({
            "id": p.get("id") or f"p-{uuid.uuid4().hex[:8]}",
            "name": (p.get("name") or "未命名").strip(),
            "text": p["text"].strip(), "question_type": qt, "is_default": is_def,
            "focus_node_ids": fids,
            "min_kp": mn, "max_kp": mx, "focus_ranges": focus_ranges,
        })
    # 每题型若无默认,把该型第一个置默认
    for t in ALL_TYPES:
        group = [p for p in cleaned if p["question_type"] == t]
        if group and not any(p["is_default"] for p in group):
            group[0]["is_default"] = True
    key = _scoped_key(scope)
    desc = "知识点 AI 建议提示词(按题型)" + (f" · 学期定制 {scope}" if scope else " · 全局默认")
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    value = {"prompts": cleaned}
    # 短文技能类开关:显式传则存,否则保留原值
    if passage_include_skill is not None:
        value["passage_include_skill"] = bool(passage_include_skill)
    elif cfg is not None and isinstance(cfg.value, dict) and "passage_include_skill" in cfg.value:
        value["passage_include_skill"] = cfg.value["passage_include_skill"]
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=key, value=value,
                            description=desc, updated_by=updated_by))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    await db.flush()
    return cleaned


async def list_scopes(db: AsyncSession) -> list[str]:
    """已定制(有独立提示词覆盖)的学期 scope 串列表。"""
    rows = (await db.execute(
        select(SystemConfig.key).where(SystemConfig.key.like(f"{_KEY}::%")))).scalars().all()
    pre = f"{_KEY}::"
    return sorted(k[len(pre):] for k in rows)


async def delete_scope(db: AsyncSession, scope: str) -> bool:
    """删除某学期的提示词定制,恢复为继承全局默认。返回是否删到。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _scoped_key(scope)))).scalar_one_or_none()
    if cfg is None:
        return False
    await db.delete(cfg)
    await db.flush()
    return True


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
            "min_kp": rng[0], "max_kp": rng[1], "focus_ranges": {}}


def item_by_id(prompts: list[dict], prompt_id: str | None) -> dict | None:
    for p in prompts:
        if p["id"] == prompt_id:
            return p
    return None
