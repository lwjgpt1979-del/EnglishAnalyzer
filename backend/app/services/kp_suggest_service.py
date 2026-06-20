"""真题 → 受控考点 AI 建议(母题挂 KP 提效)。

KV 缓存优化(https://api-docs.deepseek.com/zh-cn/guides/kv_cache):
把**稳定不变的「知识点目录(编码+名称+详解)」放进 system 消息当缓存前缀**——无论哪个
题型、哪份卷,该前缀逐 token 一致 → 命中 DeepSeek KV 缓存;把**可变的(题型提示词 +
本大题短文 + 小题)放进 user 消息**(在前缀之后)。

按 question_type 分组,各用「题型 AI 提示词」(kp_prompt_service)做 user 端指引;
LLM 用短「编码/序号」回映(避免 UUID 抄错),服务端映射回真实 node_id / question_id。
建议**不自动挂**,返回 {question_id: [(node_id, name, code)]}。dev-mock 跳过 LLM。
"""
from __future__ import annotations

import json
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, Passage
from app.models.d19_node_resource import NodeResource
from app.services import kp_prompt_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_KAODIAN_RE = r"^(cf|jf)-[0-9]+-[0-9]+-[0-9]+$"   # 四段 = 考点叶子

# system 前缀固定开头(与目录拼成稳定缓存前缀)
_SYS_HEAD = (
    "你是初中英语考点标注专家。下面给出受控「知识点目录」,每行:编码<TAB>名称<TAB>释义。\n"
    "规则:只能从该目录为题目挑考点并返回其编码;不得编造目录外的编码;每道小题最多挑 2 个"
    "最贴切的考点,无明确考点给空数组。严格输出 JSON,不要任何解释。\n\n【知识点目录】\n"
)


def _gist(md: str | None) -> str:
    """从讲解 markdown 取一句释义(跳过标题/表格/空行),去掉强调符,截断。"""
    for ln in (md or "").splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and not s.startswith("|"):
            return re.sub(r"[*_`]", "", s.lstrip("-• ")).replace("\t", " ")[:70]
    return ""


async def _load_catalog(db: AsyncSession) -> tuple[dict, str]:
    """考点目录 + 释义。返回 (code2node, system 稳定消息)。"""
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
                  NodeResource.content_md)
        .outerjoin(NodeResource, sa.and_(
            NodeResource.node_id == KnowledgeNode.id,
            NodeResource.resource_type == "lecture"))
        .where(KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active",
               KnowledgeNode.code.op("~")(_KAODIAN_RE))
        .order_by(KnowledgeNode.code)
    )).all()
    code2node: dict[str, tuple[uuid.UUID, str]] = {}
    lines: list[str] = []
    for nid, nm, code, md in rows:
        if code in code2node:
            continue
        code2node[code] = (nid, nm)
        lines.append(f"{code}\t{nm}\t{_gist(md)}")
    return code2node, _SYS_HEAD + "\n".join(lines)


async def _passages_for(db: AsyncSession, block_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = list({b for b in block_ids if b})
    if not ids:
        return {}
    rows = (await db.execute(sa.select(Passage.id, Passage.text).where(Passage.id.in_(ids)))).all()
    return {pid: (txt or "") for pid, txt in rows}


async def _suggest_group(group: list[PlatformQuestion], code2node: dict, system_msg: str,
                         type_prompt: str, passages: dict[uuid.UUID, str]) -> dict[uuid.UUID, list[tuple]]:
    """同题型一组题调一次 LLM(system=稳定目录前缀,user=题型提示词+短文+小题)。"""
    out = {q.id: [] for q in group}
    q_by_idx = {i: q for i, q in enumerate(group)}

    # 本组涉及的短文,按 A/B/C 标号(供小题引用)
    blk_label: dict[uuid.UUID, str] = {}
    for q in group:
        if q.block_id and q.block_id in passages and q.block_id not in blk_label:
            blk_label[q.block_id] = chr(ord("A") + len(blk_label))
    mat = "".join(f"[材料{lab}] {passages[bid][:600]}\n"
                  for bid, lab in blk_label.items())

    qlines = "\n".join(
        f"#{i}\t[{q.section or ''}{('·材料' + blk_label[q.block_id]) if q.block_id in blk_label else ''}]\t"
        f"{(q.stem or '').replace(chr(10), ' ')[:160]}"
        for i, q in q_by_idx.items())

    user = (
        f"{type_prompt}\n\n"
        + (f"【本大题短文/材料】\n{mat}\n" if mat else "")
        + f"【小题(#序号<TAB>[大题·材料]<TAB>题干)】\n{qlines}\n\n"
        '返回 JSON:{"items":[{"i":序号,"codes":["编码",...]}]};只用目录里的编码,无明确考点给 []。'
    )
    try:
        resp = await chat_completion(
            system_prompt=system_msg, user_prompt=user, max_tokens=4096,
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
    """按题型分组建议考点;sections 过滤、prompt_text 覆盖(供一键挂)。"""
    stmt = sa.select(PlatformQuestion).where(
        PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
    if sections:
        stmt = stmt.where(PlatformQuestion.section.in_(sections))
    qs = list((await db.execute(stmt)).scalars().all())
    if not qs or is_llm_dev_mode():
        return {q.id: [] for q in qs}

    code2node, system_msg = await _load_catalog(db)        # 稳定缓存前缀
    passages = await _passages_for(db, [q.block_id for q in qs])
    prompts = await kp_prompt_service.get_prompts(db)

    groups: dict[str, list[PlatformQuestion]] = {}
    for q in qs:
        groups.setdefault(q.question_type or "单选", []).append(q)

    out: dict[uuid.UUID, list[tuple]] = {q.id: [] for q in qs}
    for qtype, group in groups.items():
        tp = prompt_text or kp_prompt_service.default_prompt_for(prompts, qtype)
        out.update(await _suggest_group(group, code2node, system_msg, tp, passages))
    return out
