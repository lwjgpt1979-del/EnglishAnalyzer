"""真题 → 受控词法/句法考点 AI 建议(母题挂 KP 提效)。

按题型分组,各用「题型 AI 提示词」(kp_prompt_service,可配置多套选默认)在受控考点目录
(cf-*/jf-* 四段考点)里为每题挑 1-2 个考点;技能题(阅读/写作)按其提示词多半返回空。
支持按 sections 过滤(供「一键挂某大题」)+ prompt_text 覆盖(用所选提示词)。
建议**不自动挂**,返回给前端人工确认。dev-mock(占位 key)跳过 LLM 返回空。
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion
from app.services import kp_prompt_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_KAODIAN_RE = r"^(cf|jf)-[0-9]+-[0-9]+-[0-9]+$"   # 四段 = 考点叶子


async def _load_catalog(db: AsyncSession):
    nodes = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code).where(
            KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active",
            KnowledgeNode.code.op("~")(_KAODIAN_RE))
    )).all()
    code2node = {c: (nid, nm) for nid, nm, c in nodes}
    catalog = "\n".join(f"{c}\t{nm}" for nid, nm, c in nodes)
    return code2node, catalog


async def _suggest_group(group: list[PlatformQuestion], code2node: dict, catalog: str,
                         system_prompt: str) -> dict[uuid.UUID, list[tuple]]:
    """对同题型一组题调一次 LLM,返回 {qid: [(node_id,name,code)]}。"""
    out = {q.id: [] for q in group}
    q_by_idx = {i: q for i, q in enumerate(group)}
    qlines = "\n".join(
        f"#{i}\t[{q.section or ''}] {(q.stem or '').replace(chr(10), ' ')[:140]}"
        for i, q in q_by_idx.items())
    user = (
        f"【考点目录(编码<TAB>名称)】\n{catalog}\n\n"
        f"【题目(#序号<TAB>[大题] 题干)】\n{qlines}\n\n"
        '返回 JSON:{"items":[{"i":序号,"codes":["编码",...]}, ...]};'
        "按上述要求给每题挑考点编码(无则空数组),只用目录里的编码。"
    )
    try:
        resp = await chat_completion(
            system_prompt=system_prompt, user_prompt=user, max_tokens=4096,
            response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return out
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


async def suggest_kps_for_paper(
    db: AsyncSession, paper_id: uuid.UUID, *,
    sections: list[str] | None = None, prompt_text: str | None = None,
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]]:
    """按题型分组用各自默认提示词建议考点;sections 过滤、prompt_text 覆盖(供一键挂)。"""
    stmt = sa.select(PlatformQuestion).where(
        PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
    if sections:
        stmt = stmt.where(PlatformQuestion.section.in_(sections))
    qs = list((await db.execute(stmt)).scalars().all())
    if not qs or is_llm_dev_mode():
        return {q.id: [] for q in qs}

    code2node, catalog = await _load_catalog(db)
    prompts = await kp_prompt_service.get_prompts(db)

    groups: dict[str, list[PlatformQuestion]] = {}
    for q in qs:
        groups.setdefault(q.question_type or "单选", []).append(q)

    out: dict[uuid.UUID, list[tuple]] = {q.id: [] for q in qs}
    for qtype, group in groups.items():
        sys = prompt_text or kp_prompt_service.default_prompt_for(prompts, qtype)
        out.update(await _suggest_group(group, code2node, catalog, sys))
    return out
