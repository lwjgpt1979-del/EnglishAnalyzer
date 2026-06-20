"""真题 → 受控词法/句法考点 AI 建议(母题挂 KP 提效)。

给每道语法类题在受控考点树(cf-*/jf-* 四段考点)里挑 1-2 个最相近考点;
听力/阅读/完形/写作等技能题返回空(那些用「按大题一键挂」挂能力/题型轴)。
建议**不自动挂**,返回给前端人工确认。dev-mock(占位 key)跳过 LLM 返回空。
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_KAODIAN_RE = r"^(cf|jf)-[0-9]+-[0-9]+-[0-9]+$"   # 四段 = 考点叶子

_SYSTEM = (
    "你是初中英语命题考点标注专家。给定一份受控「考点目录」和若干题目,"
    "为每道**语法类**题(单项填空/语法填空/完成句子等)从目录里挑最贴切的 1-2 个考点编码;"
    "听力/阅读理解/完形/信息还原/书面表达等技能题返回空数组。只能用目录里出现的编码,"
    "严格输出 JSON,不要解释。"
)


async def suggest_kps_for_paper(
    db: AsyncSession, paper_id: uuid.UUID
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]]:
    """返回 {question_id: [(node_id, name, code), ...]}(建议,未挂)。"""
    qs = list((await db.execute(
        sa.select(PlatformQuestion).where(
            PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
    )).scalars().all())
    if not qs or is_llm_dev_mode():
        return {q.id: [] for q in qs}

    nodes = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code).where(
            KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active",
            KnowledgeNode.code.op("~")(_KAODIAN_RE))
    )).all()
    code2node: dict[str, tuple[uuid.UUID, str]] = {c: (nid, nm) for nid, nm, c in nodes}
    catalog = "\n".join(f"{c}\t{nm}" for nid, nm, c in nodes)

    q_by_idx = {i: q for i, q in enumerate(qs)}
    qlines = "\n".join(
        f"#{i}\t[{q.section or ''}] {(q.stem or '').replace(chr(10), ' ')[:140]}"
        for i, q in q_by_idx.items())

    user = (
        f"【考点目录(编码<TAB>名称)】\n{catalog}\n\n"
        f"【题目(#序号<TAB>[大题] 题干)】\n{qlines}\n\n"
        '返回 JSON:{"items":[{"i":序号,"codes":["编码",...]}, ...]};'
        "语法题给 1-2 个最贴切考点编码,技能题 codes 给 []。只用目录里的编码。"
    )
    try:
        resp = await chat_completion(
            system_prompt=_SYSTEM, user_prompt=user, max_tokens=4096,
            response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return {q.id: [] for q in qs}

    out: dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]] = {q.id: [] for q in qs}
    for it in (data.get("items") or []):
        q = q_by_idx.get(it.get("i"))
        if q is None:
            continue
        seen: set[uuid.UUID] = set()
        for code in (it.get("codes") or [])[:2]:
            ref = code2node.get(code)
            if ref and ref[0] not in seen:
                seen.add(ref[0])
                out[q.id].append((ref[0], ref[1], code))
    return out
