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
QUESTION_TYPES = ["单选", "填空", "完型", "阅读", "写作"]

# 内置默认提示词:仅"该题型怎么挑"的指引(放 user 端);
# 角色、知识点目录、输出 JSON 格式由 kp_suggest_service 的稳定 system 前缀统一给出。
_BUILTIN: dict[str, str] = {
    "单选": "【本大题:单项填空 / 语法选择】主要考语法与词汇辨析。为每道小题挑 1-2 个最贴切的"
            "语法或词汇考点(如时态、介词、从句、词义辨析等)。",
    "填空": "【本大题:单词拼写 / 选词填空 / 完成句子】考词汇运用与基础语法。为每题挑 1-2 个"
            "最贴切的词汇或语法考点。",
    "完型": "【本大题:完形填空】每空考查一个词汇/语法/语境点。请结合短文语境,为每空挑 1-2 个"
            "最贴切的考点(动词词义、固定搭配、连词、时态等)。",
    "阅读": "【本大题:阅读理解 / 信息还原】主要考阅读理解与篇章能力,多数小题不对应具体语言考点。"
            "仅当某题明确考查某语法/词汇/篇章考点时才挑 1 个,否则 codes 给空数组。",
    "写作": "【本大题:书面表达】综合性写作,一般不对应单一语言考点。codes 一律给空数组,"
            "除非题干明确限定考查某语法点。",
}


def _builtin_list() -> list[dict]:
    return [{"id": f"builtin-{t}", "name": "内置默认", "text": _BUILTIN[t],
             "question_type": t, "is_default": True, "focus_node_ids": []}
            for t in QUESTION_TYPES]


async def get_prompts(db: AsyncSession) -> list[dict]:
    """读全部提示词;缺失返回内置默认(每题型一条)。"""
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None or not isinstance(cfg.value, dict) or not cfg.value.get("prompts"):
        return _builtin_list()
    return cfg.value["prompts"]


async def save_prompts(db: AsyncSession, *, prompts: list[dict], updated_by: uuid.UUID) -> list[dict]:
    """保存提示词(整体覆盖)。每题型至多一个 is_default;补 id。"""
    cleaned: list[dict] = []
    seen_default: set[str] = set()
    for p in prompts:
        qt = p.get("question_type")
        if qt not in QUESTION_TYPES or not (p.get("text") or "").strip():
            continue
        is_def = bool(p.get("is_default")) and qt not in seen_default
        if is_def:
            seen_default.add(qt)
        cleaned.append({
            "id": p.get("id") or f"p-{uuid.uuid4().hex[:8]}",
            "name": (p.get("name") or "未命名").strip(),
            "text": p["text"].strip(), "question_type": qt, "is_default": is_def,
            "focus_node_ids": [str(x) for x in (p.get("focus_node_ids") or [])],
        })
    # 每题型若无默认,把该型第一个置默认
    for t in QUESTION_TYPES:
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
    return {"text": _BUILTIN.get(qt, _BUILTIN["单选"]), "focus_node_ids": []}


def item_by_id(prompts: list[dict], prompt_id: str | None) -> dict | None:
    for p in prompts:
        if p["id"] == prompt_id:
            return p
    return None
