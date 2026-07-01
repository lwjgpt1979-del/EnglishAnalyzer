"""上传长难句:粘贴一段文字 → LLM 抽语法点(+例句)落成 long_sentence 草稿,
再逐点人工挂靠到知识图谱(词法 cf / 句法 jf 子树),挂边落 long_sentence_node。

与「单元解析」体验一致:挂靠/改挂/新建节点;挂靠时把语法点名沉淀为节点别称。
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services.kp_normalize import normalize_kp_name

_SYS = (
    "你是初中英语语法分析专家。给你一段英文(可能是长难句/课文片段)。请抽出其中涉及的**语法点(词法/句法)**,"
    "每个语法点给一个**来自原文的英文例句**。\n"
    "**只收真正的语法点**(如 定语从句、宾语从句、动词不定式、现在完成时、被动语态、比较级、非谓语动词…),"
    "**严禁把交际功能/话题功能当语法点**(自我介绍、询问信息、表达观点 等一律不要)。\n"
    "语法点名用中文。互不重叠、紧扣原文真正出现的结构,不臆造。严格输出 JSON,不要解释。"
)


async def parse_and_persist(db: AsyncSession, *, text: str,
                            unit_id: uuid.UUID | None = None) -> list[dict]:
    """LLM 抽语法点+例句 → 每点落一条 long_sentence 草稿(source_kind=uploaded)。返回行列表。

    unit_id 给定时:把长难句归属该课程单元(unit_id + 教材版/年级/学期/学段定位回填)。
    """
    from app.services.llm_provider import chat_completion, is_llm_dev_mode, fast_model
    from app.services.long_sentence_service import syntactic_complexity, _stage_from_grade
    body = (text or "").strip()
    if not body:
        raise AppError(code=400, message="请输入文字")
    locate: dict = {}
    if unit_id is not None:
        from app.models.d4_knowledge import CurriculumUnit
        unit = await db.get(CurriculumUnit, unit_id)
        if unit is None:
            raise AppError(code=404, message="单元不存在")
        locate = {"unit_id": unit_id, "textbook_version": unit.textbook_version,
                  "grade": unit.grade, "semester": unit.semester,
                  "stage": _stage_from_grade(unit.grade)}
    if is_llm_dev_mode():
        return []
    user = (
        f"文字:\n{body[:5000]}\n\n"
        '抽出语法点,输出 JSON:{"points":[{"point":"中文语法点名","sent":"原文英文例句"}]}。'
        "只取原文真正出现的语法结构;不要交际功能。只返回纯 JSON。")
    try:
        resp = await chat_completion(system_prompt=_SYS, user_prompt=user, model=fast_model(),
                                     max_tokens=8192, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        raise AppError(code=502, message="LLM 解析失败,请重试")
    points = data.get("points") if isinstance(data, dict) else None
    out: list[dict] = []
    seen: set[str] = set()
    for it in (points or []):
        if not isinstance(it, dict):
            continue
        pname = (it.get("point") or "").strip()
        sent = (it.get("sent") or "").strip()
        if not pname or not sent or pname in seen:
            continue
        seen.add(pname)
        diff = None
        try:
            diff = syntactic_complexity(sent).get("difficulty")
        except Exception:  # noqa: BLE001
            diff = None
        ls = LongSentence(
            id=uuid.uuid4(), scope="platform", source_kind="uploaded", status="draft",
            text=sent, difficulty=diff,
            analysis_json={"syntax_points": [pname], "source": "upload"},
            unit_id=locate.get("unit_id"), textbook_version=locate.get("textbook_version"),
            grade=locate.get("grade"), semester=locate.get("semester"), stage=locate.get("stage"))
        db.add(ls)
        await db.flush()
        out.append({"id": str(ls.id), "point": pname, "text": sent, "difficulty": diff,
                    "node_id": None, "node_code": None, "node_name": None})
    return out


def _point_of(ls: LongSentence) -> str:
    sp = (ls.analysis_json or {}).get("syntax_points") or []
    return sp[0] if sp else (ls.text or "")[:40]


async def list_recent(db: AsyncSession, *, limit: int = 50,
                      unit_id: uuid.UUID | None = None) -> list[dict]:
    """最近上传的长难句草稿(含已挂节点),供弹框回看/管理。unit_id 给定则只看该单元。"""
    stmt = sa.select(LongSentence).where(LongSentence.source_kind == "uploaded")
    if unit_id is not None:
        stmt = stmt.where(LongSentence.unit_id == unit_id)
    rows = (await db.execute(
        stmt.order_by(LongSentence.created_at.desc()).limit(limit))).scalars().all()
    if not rows:
        return []
    ids = [r.id for r in rows]
    edges = (await db.execute(
        sa.select(LongSentenceNode.long_sentence_id, KnowledgeNode.id, KnowledgeNode.code, KnowledgeNode.name)
        .join(KnowledgeNode, KnowledgeNode.id == LongSentenceNode.node_id)
        .where(LongSentenceNode.long_sentence_id.in_(ids)))).all()
    emap = {e[0]: (e[1], e[2], e[3]) for e in edges}
    out = []
    for r in rows:
        e = emap.get(r.id)
        out.append({"id": str(r.id), "point": _point_of(r), "text": r.text, "difficulty": r.difficulty,
                    "node_id": str(e[0]) if e else None, "node_code": e[1] if e else None,
                    "node_name": e[2] if e else None})
    return out


async def auto_link_unit(db: AsyncSession, *, unit_id: uuid.UUID) -> dict:
    """对该单元**未挂**的上传长难句:用语法点名做分词打分,匹配 cf/jf 里最高分节点(≥阈值)自动挂边。

    与「单元解析」自动关联同款:别名/节点名建候选,Dice 系数取最高分;不走 LLM。返回计数。
    """
    from app.services.curriculum_service import (kp_match_tokens, kp_match_score,
                                                 KP_AUTO_LINK_THRESHOLD)
    allowed = await _grammar_subtree(db)
    out = {"linked": 0, "unmatched": 0, "skipped": 0}
    if not allowed:
        return out
    # 候选 = 子树内每个节点的(名称 + 别名)
    cands: list[dict] = []
    for n in (await db.execute(sa.select(KnowledgeNode.id, KnowledgeNode.code, KnowledgeNode.name)
                               .where(KnowledgeNode.id.in_(allowed)))).all():
        cands.append({"node_id": n.id, "code": n.code,
                      "norm": normalize_kp_name(n.name or ""), "tokens": kp_match_tokens(n.name or "")})
    for a in (await db.execute(sa.select(NodeAlias.alias, NodeAlias.alias_norm, NodeAlias.node_id, KnowledgeNode.code)
                               .join(KnowledgeNode, KnowledgeNode.id == NodeAlias.node_id)
                               .where(NodeAlias.node_id.in_(allowed)))).all():
        base = a.alias or a.alias_norm or ""
        cands.append({"node_id": a.node_id, "code": a.code,
                      "norm": a.alias_norm or "", "tokens": kp_match_tokens(base)})

    rows = (await db.execute(sa.select(LongSentence).where(
        LongSentence.source_kind == "uploaded", LongSentence.unit_id == unit_id))).scalars().all()
    if not rows:
        return out
    linked = set((await db.execute(sa.select(LongSentenceNode.long_sentence_id).where(
        LongSentenceNode.long_sentence_id.in_([r.id for r in rows])))).scalars().all())
    for ls in rows:
        if ls.id in linked:
            out["skipped"] += 1
            continue
        name = _point_of(ls)
        norm = normalize_kp_name(name)
        if not norm:
            out["unmatched"] += 1
            continue
        qt = kp_match_tokens(name)
        best, best_score = None, 0.0
        for c in cands:
            score = 1.0 if (c["norm"] and c["norm"] == norm) else kp_match_score(qt, c["tokens"])
            if score > best_score:
                best, best_score = c, score
        if best is not None and best_score >= KP_AUTO_LINK_THRESHOLD:
            db.add(LongSentenceNode(long_sentence_id=ls.id, node_id=best["node_id"]))
            out["linked"] += 1
        else:
            out["unmatched"] += 1
    await db.flush()
    return out


async def _grammar_subtree(db: AsyncSession) -> set:
    from app.services.kp_suggest_service import _descendant_node_ids
    root_ids = (await db.execute(
        sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(["cf", "jf"])))).scalars().all()
    return await _descendant_node_ids(db, list(root_ids)) or set()


async def link_node(db: AsyncSession, *, ls_id: uuid.UUID, node_id: uuid.UUID) -> dict:
    """把某长难句的语法点挂靠到图谱里已存在的节点(限词法/句法子树);替换原挂边。"""
    ls = await db.get(LongSentence, ls_id)
    if ls is None:
        raise AppError(code=404, message="长难句不存在")
    allowed = await _grammar_subtree(db)
    node = await db.get(KnowledgeNode, node_id)
    if node is None or node.id not in allowed:
        raise AppError(code=400, message="所选节点不在词法/句法目录范围")
    await db.execute(sa.delete(LongSentenceNode).where(LongSentenceNode.long_sentence_id == ls_id))
    db.add(LongSentenceNode(long_sentence_id=ls_id, node_id=node.id))
    await db.flush()
    # 沉淀别称:语法点名 → 该节点
    from app.services.curriculum_service import record_node_alias
    await record_node_alias(db, node_id=node.id, raw_name=_point_of(ls), source="manual")
    return {"node_id": str(node.id), "node_code": node.code, "name": node.name}


async def new_node(db: AsyncSession, *, ls_id: uuid.UUID, parent_id: uuid.UUID,
                   name: str) -> dict:
    """目录里没有 → 在所选父分类(限 cf/jf 子树)下新建节点并挂靠。"""
    nm = (name or "").strip()
    if not nm:
        raise AppError(code=400, message="节点名不能为空")
    ls = await db.get(LongSentence, ls_id)
    if ls is None:
        raise AppError(code=404, message="长难句不存在")
    allowed = await _grammar_subtree(db)
    parent = await db.get(KnowledgeNode, parent_id)
    if parent is None or parent.id not in allowed:
        raise AppError(code=400, message="父分类不在词法/句法目录范围")
    code = f"m-{uuid.uuid4().hex[:10]}"
    node = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", parent_id=parent.id, name=nm[:120],
                         code=code, status="active", source="manual",
                         applicable_stages=parent.applicable_stages)
    db.add(node)
    await db.flush()
    db.add(NodeAlias(id=uuid.uuid4(), node_id=node.id, alias=nm[:120],
                     alias_norm=normalize_kp_name(nm), source="manual"))
    await db.execute(sa.delete(LongSentenceNode).where(LongSentenceNode.long_sentence_id == ls_id))
    db.add(LongSentenceNode(long_sentence_id=ls_id, node_id=node.id))
    await db.flush()
    from app.services.kp_candidate_service import invalidate_node_tree_cache
    invalidate_node_tree_cache()
    return {"node_id": str(node.id), "node_code": code, "name": nm}


async def delete_uploaded(db: AsyncSession, *, ls_id: uuid.UUID) -> None:
    ls = await db.get(LongSentence, ls_id)
    if ls is None or ls.source_kind != "uploaded":
        raise AppError(code=404, message="长难句不存在")
    await db.execute(sa.delete(LongSentenceNode).where(LongSentenceNode.long_sentence_id == ls_id))
    await db.delete(ls)
    await db.flush()
