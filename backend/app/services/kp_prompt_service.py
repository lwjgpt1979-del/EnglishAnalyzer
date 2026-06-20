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

# 内置默认提示词(system 角色指令);user 提示由 suggest 拼"考点目录+题目"
_BUILTIN: dict[str, str] = {
    "单选": "你是初中英语考点标注专家。下面是单项填空/语法选择题,请从给定受控考点目录里为每题挑"
            "最贴切的 1-2 个语法或词汇考点编码;只能用目录内编码,无明确考点给空数组。严格输出 JSON。",
    "填空": "你是初中英语考点标注专家。下面是单词拼写/选词/完成句子等填空题,请从受控考点目录里挑"
            "最贴切的 1-2 个词汇或语法考点编码;只用目录内编码,严格输出 JSON。",
    "完型": "你是初中英语考点标注专家。下面是完形填空小题(每空考查一个词汇/语法/篇章点),请从受控"
            "考点目录里为每空挑该空考查的 1-2 个考点编码;只用目录内编码,严格输出 JSON。",
    "阅读": "你是初中英语考点标注专家。下面是阅读理解/信息还原题,主要考阅读与篇章能力。若题干明确"
            "考查某语法/词汇/篇章考点则从目录挑 1 个,否则 codes 给空数组。只用目录内编码,严格输出 JSON。",
    "写作": "你是初中英语考点标注专家。下面是书面表达题,综合考查,一般不挂具体语言考点,codes 一律"
            "给空数组(除非题干明确限定某语法点)。严格输出 JSON。",
}


def _builtin_list() -> list[dict]:
    return [{"id": f"builtin-{t}", "name": "内置默认", "text": _BUILTIN[t],
             "question_type": t, "is_default": True} for t in QUESTION_TYPES]


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


def default_prompt_for(prompts: list[dict], qtype: str | None) -> str:
    """取某题型的默认提示词文本;无配置回内置;再无回单选内置。"""
    qt = qtype or "单选"
    for p in prompts:
        if p["question_type"] == qt and p.get("is_default"):
            return p["text"]
    for p in prompts:
        if p["question_type"] == qt:
            return p["text"]
    return _BUILTIN.get(qt, _BUILTIN["单选"])


def prompt_by_id(prompts: list[dict], prompt_id: str | None) -> str | None:
    for p in prompts:
        if p["id"] == prompt_id:
            return p["text"]
    return None
