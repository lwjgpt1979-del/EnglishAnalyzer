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
from app.models.d16_question_domain import PlatformPaper, PlatformQuestion, Passage
from app.models.d19_node_resource import NodeResource
from app.services import kp_prompt_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_KAODIAN_RE = r"^(cf|jf)-[0-9]+-[0-9]+-[0-9]+$"   # 四段 = 考点叶子

# 学段包含关系:高 ⊇ 初 ⊇ 小。匹配某学段卷时,该学段「及更低」的考点都算候选。
_STAGE_RANK = {"小": 0, "初": 1, "高": 2}


def _stages_at_or_below(stage: str | None) -> list[str] | None:
    """某学段可用的考点学段集合(含更低)。None=不限(返回 None 表示不过滤)。"""
    pr = _STAGE_RANK.get(stage or "")
    if pr is None:
        return None
    return [s for s, r in _STAGE_RANK.items() if r <= pr]


def _stage_allows(cand_stages: list | None, allowed: list[str] | None) -> bool:
    """考点是否适用:通用(未标)恒可;否则其任一学段落在 allowed 集合内。"""
    if allowed is None or not cand_stages:
        return True
    return any(s in allowed for s in cand_stages)

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


async def _load_catalog(db: AsyncSession) -> tuple[dict, list[tuple[str, str, list]]]:
    """考点目录 + 释义。返回 (code2node, entries[(code, 行文本, 适用学段)])。"""
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
                  KnowledgeNode.applicable_stages, NodeResource.content_md)
        .outerjoin(NodeResource, sa.and_(
            NodeResource.node_id == KnowledgeNode.id,
            NodeResource.resource_type == "lecture"))
        .where(KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active",
               KnowledgeNode.code.op("~")(_KAODIAN_RE))
        .order_by(KnowledgeNode.code)
    )).all()
    code2node: dict[str, tuple[uuid.UUID, str]] = {}
    entries: list[tuple[str, str, list]] = []
    for nid, nm, code, stages, md in rows:
        if code in code2node:
            continue
        code2node[code] = (nid, nm)
        entries.append((code, f"{code}\t{nm}\t{_gist(md)}", stages or []))
    return code2node, entries


def _system_for(entries: list[tuple[str, str, list]], focus_codes: list[str],
                stage: str | None = None) -> str:
    """过滤考点目录拼稳定 system 前缀。focus=关注分类编码前缀(空=全部);
    stage=题/卷学段过滤,包含式(高⊇初⊇小):该学段及更低的考点 + 通用考点都纳入。"""
    fc = [c for c in focus_codes if c] if focus_codes else None
    allowed = _stages_at_or_below(stage)
    lines: list[str] = []
    for code, ln, stages in entries:
        if fc and not any(code == f or code.startswith(f + "-") for f in fc):
            continue
        if not _stage_allows(stages, allowed):
            continue
        lines.append(ln)
    return _SYS_HEAD + "\n".join(lines)


async def _passages_for(db: AsyncSession, block_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = list({b for b in block_ids if b})
    if not ids:
        return {}
    rows = (await db.execute(sa.select(Passage.id, Passage.text).where(Passage.id.in_(ids)))).all()
    return {pid: (txt or "") for pid, txt in rows}


async def _suggest_group(group: list[PlatformQuestion], code2node: dict, system_msg: str,
                         type_prompt: str, passages: dict[uuid.UUID, str],
                         min_kp: int = 0, max_kp: int = 2) -> dict[uuid.UUID, list[tuple]]:
    """同题型一组题调一次 LLM(system=稳定目录前缀,user=题型提示词+短文+小题)。"""
    out = {q.id: [] for q in group}
    # 短 id(question_id 前 8 位 hex)做小题标识——不与题干里的题号(8.9.…)相混
    by_qid: dict[str, PlatformQuestion] = {}
    for q in group:
        k = str(q.id)[:8]
        while k in by_qid:          # 极罕见前缀碰撞 → 加长
            k = str(q.id)[:len(k) + 4]
        by_qid[k] = q
    q_qid = {q.id: k for k, q in by_qid.items()}

    # 本组涉及的短文,按 A/B/C 标号(供小题引用)
    blk_label: dict[uuid.UUID, str] = {}
    for q in group:
        if q.block_id and q.block_id in passages and q.block_id not in blk_label:
            blk_label[q.block_id] = chr(ord("A") + len(blk_label))
    mat = "".join(f"[材料{lab}] {passages[bid][:600]}\n"
                  for bid, lab in blk_label.items())

    qlines = "\n".join(
        f"qid={q_qid[q.id]}\t[{q.section or ''}{('·材料' + blk_label[q.block_id]) if q.block_id in blk_label else ''}]\t"
        f"{(q.stem or '').replace(chr(10), ' ')[:160]}"
        for q in group)

    cnt = (f"每题挑 {min_kp}-{max_kp} 个" if min_kp else f"每题挑至多 {max_kp} 个") + "最贴切考点(无明确考点给 [])。"
    user = (
        f"{type_prompt}\n{cnt}\n\n"
        + (f"【本大题短文/材料】\n{mat}\n" if mat else "")
        + f"【小题(qid<TAB>[大题·材料]<TAB>题干)】\n{qlines}\n\n"
        '返回 JSON:{"items":[{"qid":"小题qid","codes":["编码",...]}]};qid 原样回传,只用目录里的编码。'
    )
    try:
        resp = await chat_completion(
            system_prompt=system_msg, user_prompt=user, max_tokens=4096,
            response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return out
    for it in (data.get("items") or []):
        q = by_qid.get(str(it.get("qid")))
        if q is None:
            continue
        seen: set[uuid.UUID] = set()
        for code in (it.get("codes") or [])[:max_kp]:
            ref = code2node.get(code)
            if ref and ref[0] not in seen:
                seen.add(ref[0])
                out[q.id].append((ref[0], ref[1], code))
    return out


async def suggest_kps_for_text(
    db: AsyncSession, text: str, *, source_type: str = "教材", stage: str | None = None,
) -> list[tuple[uuid.UUID, str, str]]:
    """一段正文(教材等)→ 受控考点建议。用该来源类型的提示词 + 关注分类 + 学段过滤目录。"""
    if not (text or "").strip() or is_llm_dev_mode():
        return []
    code2node, entries = await _load_catalog(db)
    prompts = await kp_prompt_service.get_prompts(db)
    item = kp_prompt_service.default_item_for(prompts, source_type)
    id2code = await _codes_of_nodes(db, item.get("focus_node_ids") or [])
    focus_codes = [id2code[str(n)] for n in (item.get("focus_node_ids") or []) if str(n) in id2code]
    system_msg = _system_for(entries, focus_codes, stage)
    max_kp = int(item.get("max_kp", 8))
    user = (
        f"{item['text']}\n挑出正文覆盖到的考点(至多 {max_kp} 个)。\n\n【正文】\n{text[:4000]}\n\n"
        '返回 JSON:{"codes":["编码",...]};只用目录里的编码。'
    )
    try:
        resp = await chat_completion(system_prompt=system_msg, user_prompt=user,
                                     max_tokens=2048, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for code in (data.get("codes") or [])[:max_kp]:
        ref = code2node.get(code)
        if ref and ref[0] not in seen:
            seen.add(ref[0])
            out.append((ref[0], ref[1], code))
    return out


async def _codes_of_nodes(db: AsyncSession, node_ids: list) -> dict[str, str]:
    """node_id(str)→ code,用于把关注分类解析成编码前缀。"""
    if not node_ids:
        return {}
    rows = (await db.execute(sa.select(KnowledgeNode.id, KnowledgeNode.code)
                             .where(KnowledgeNode.id.in_(node_ids)))).all()
    return {str(nid): code for nid, code in rows}


async def suggest_kps_for_paper(
    db: AsyncSession, paper_id: uuid.UUID, *,
    sections: list[str] | None = None, prompt_id: str | None = None,
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]]:
    """按题型分组建议考点;每题型用其(默认/指定)提示词 + 关注分类过滤目录。"""
    stmt = sa.select(PlatformQuestion).where(
        PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
    if sections:
        stmt = stmt.where(PlatformQuestion.section.in_(sections))
    qs = list((await db.execute(stmt)).scalars().all())
    if not qs or is_llm_dev_mode():
        return {q.id: [] for q in qs}

    code2node, entries = await _load_catalog(db)
    passages = await _passages_for(db, [q.block_id for q in qs])
    prompts = await kp_prompt_service.get_prompts(db)
    override = kp_prompt_service.item_by_id(prompts, prompt_id) if prompt_id else None
    # 卷的学段(优先卷,回退小题)→ 候选考点按学段软过滤(未标学段=通用)
    stage = (await db.execute(sa.select(PlatformPaper.stage)
                              .where(PlatformPaper.id == paper_id))).scalar_one_or_none()
    if not stage:
        stage = next((q.stage for q in qs if getattr(q, "stage", None)), None)

    def _etype(q: PlatformQuestion) -> str:        # 听力题(section 含"听力")单列题型
        if "听力" in (q.section or ""):
            return "听力"
        return q.question_type or "单选"

    groups: dict[str, list[PlatformQuestion]] = {}
    for q in qs:
        groups.setdefault(_etype(q), []).append(q)

    # 解析各题型关注分类 → 编码
    items = {qt: (override or kp_prompt_service.default_item_for(prompts, qt)) for qt in groups}
    all_focus = {nid for it in items.values() for nid in (it.get("focus_node_ids") or [])}
    id2code = await _codes_of_nodes(db, list(all_focus))

    out: dict[uuid.UUID, list[tuple]] = {q.id: [] for q in qs}
    for qtype, group in groups.items():
        it = items[qtype]
        focus_codes = [id2code[str(n)] for n in (it.get("focus_node_ids") or []) if str(n) in id2code]
        system_msg = _system_for(entries, focus_codes, stage)   # 题型+学段稳定前缀(同题型同学段→命中缓存)
        out.update(await _suggest_group(group, code2node, system_msg, it["text"], passages,
                                        int(it.get("min_kp", 0)), int(it.get("max_kp", 2))))
    return out
