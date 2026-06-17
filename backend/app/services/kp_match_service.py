"""R0.3 受控匹配服务(替换"自由命名 + 按名精确 + 建 auto_ 点")。

输入抽取出的"知识点名 + 上下文",尽量命中已有 knowledge_node,命中不了才
累加 kp_candidate(occur_count++),**绝不**自动建游离节点。

匹配管线(短路顺序,设计 §3):
  1. 归一化精确:name_norm 命中 node_alias.alias_norm → 命中(alias)
  2. 受控选择(LLM):把该 axis(+学段)下节点清单喂 LLM,从清单里选;选不中=NONE
  3. 模糊兜底:与清单节点名/别名做相似度,过阈值取最近 → fuzzy(置信度低,建议复核)
  4. 都不中 → 写/累加 kp_candidate(pending),不建节点

dev 模式(is_llm_dev_mode)下第 2 步用确定性"包含关系"代理 LLM 选择,保证可测。
"""
from __future__ import annotations

import difflib
import json
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.services.kp_normalize import normalize_kp_name
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_log = logging.getLogger(__name__)

# 模糊兜底相似度阈值(SequenceMatcher.ratio);低于此只进候选,不强行命中
_FUZZY_THRESHOLD = 0.82
# 受控选择/模糊比对时,单 axis 取用的候选节点上限(防 prompt 过大)
_CANDIDATE_CAP = 80


@dataclass
class MatchResult:
    node_id: uuid.UUID | None
    matched_by: str               # exact | alias | controlled_llm | fuzzy | candidate | skip
    candidate_id: uuid.UUID | None
    confidence: float


@dataclass
class _NodeRef:
    node_id: uuid.UUID
    name: str
    alias_norm: str


async def _fetch_axis_refs(
    db: AsyncSession, axis: str, stage_hint: str | None
) -> list[_NodeRef]:
    """取某 axis 下 active 节点的(节点 id, 名, 别名归一键)清单。

    学段为软过滤:节点未标学段(对所有学段通用)或包含 stage_hint 才纳入。
    """
    rows = (await db.execute(
        sa.select(NodeAlias.node_id, KnowledgeNode.name,
                  NodeAlias.alias_norm, KnowledgeNode.applicable_stages)
        .join(KnowledgeNode, KnowledgeNode.id == NodeAlias.node_id)
        .where(KnowledgeNode.axis == axis, KnowledgeNode.status == "active")
    )).all()
    refs: list[_NodeRef] = []
    for node_id, name, alias_norm, stages in rows:
        if stage_hint and stages and stage_hint not in stages:
            continue
        refs.append(_NodeRef(node_id=node_id, name=name, alias_norm=alias_norm))
    return refs


def _controlled_select_dev(name_norm: str, refs: list[_NodeRef]) -> uuid.UUID | None:
    """dev 代理:确定性"包含关系"选择(模拟 LLM 从清单里认出同概念)。

    取与 name_norm 互为包含(真子串)的最贴近者;长度差最小优先。与模糊步区分:
    这里只认"包含",纯编辑距离近似留给模糊步。
    """
    best: tuple[int, uuid.UUID] | None = None
    for r in refs:
        a, b = name_norm, r.alias_norm
        if a == b:
            continue  # 相等归精确步,这里只管真包含
        if a in b or b in a:
            gap = abs(len(a) - len(b))
            if best is None or gap < best[0]:
                best = (gap, r.node_id)
    return best[1] if best else None


async def _controlled_select_llm(
    raw_name: str, refs: list[_NodeRef], context: str | None
) -> uuid.UUID | None:
    """真实 LLM:把清单编号喂模型,从清单里选;选不中返回 None。"""
    capped = refs[:_CANDIDATE_CAP]
    listing = "\n".join(f"{i}. {r.name}" for i, r in enumerate(capped))
    system = (
        "你是英语知识点对齐助手。给定一个待匹配的知识点名和一份标准知识点清单,"
        "从清单里选出**语义等同**的那一个;若清单里没有等同项,返回 NONE。"
        "严格输出 JSON,不要任何额外文字。"
    )
    user = (
        f"待匹配知识点:{raw_name}\n"
        + (f"上下文:{context}\n" if context else "")
        + f"\n标准清单:\n{listing}\n\n"
        '返回 JSON:命中则 {"choice": <编号整数>},没有等同项则 {"choice": "NONE"}'
    )
    try:
        resp = await chat_completion(
            system_prompt=system, user_prompt=user, max_tokens=64,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        choice = json.loads(raw).get("choice")
    except Exception as exc:  # LLM 不可用 → 不阻断,降级到模糊/候选
        _log.warning("controlled-select LLM failed, fallback: %s", exc)
        return None
    if isinstance(choice, int) and 0 <= choice < len(capped):
        return capped[choice].node_id
    return None


def _fuzzy_best(name_norm: str, refs: list[_NodeRef]) -> tuple[uuid.UUID | None, float]:
    """与清单别名做相似度,返回(最近节点 id, ratio);未过阈值返回(None, best_ratio)。"""
    best_id: uuid.UUID | None = None
    best_ratio = 0.0
    for r in refs:
        ratio = difflib.SequenceMatcher(None, name_norm, r.alias_norm).ratio()
        if ratio > best_ratio:
            best_ratio, best_id = ratio, r.node_id
    if best_ratio >= _FUZZY_THRESHOLD:
        return best_id, best_ratio
    return None, best_ratio


async def _upsert_candidate(
    db: AsyncSession, *, raw_name: str, name_norm: str, axis: str,
    stage_hint: str | None, source_type: str, source_ref: dict | None,
    context: str | None,
) -> uuid.UUID:
    """落/累加候选(occur_count++),返回候选 id。axis 必非空(规避唯一键 NULL 去重失效)。"""
    stmt = (
        pg_insert(KpCandidate)
        .values(
            id=uuid.uuid4(), raw_name=raw_name, name_norm=name_norm,
            suggested_axis=axis, suggested_stage=stage_hint, occur_count=1,
            context_sample=({"context": context} if context else None),
            source_type=source_type, source_ref=source_ref, status="pending",
        )
        .on_conflict_do_update(
            constraint="uix_kp_candidate_norm_axis",
            set_={"occur_count": KpCandidate.occur_count + 1},
        )
        .returning(KpCandidate.id)
    )
    return (await db.execute(stmt)).scalar_one()


async def match_kp(
    db: AsyncSession, *, raw_name: str,
    axis_hint: str = "knowledge",       # 必非空,决策②
    stage_hint: str | None = None,      # 小|初|高
    source_type: str = "uploaded_student",
    source_ref: dict | None = None,
    context: str | None = None,
    use_llm: bool = True,
) -> MatchResult:
    """受控匹配单个知识点名。命中返回 node_id;不中累加候选并返回 candidate_id。"""
    name_norm = normalize_kp_name(raw_name)
    if not name_norm:
        return MatchResult(None, "skip", None, 0.0)

    # 1) 归一化精确(别名表)
    hit = (await db.execute(
        sa.select(NodeAlias.node_id).where(NodeAlias.alias_norm == name_norm)
    )).scalar_one_or_none()
    if hit is not None:
        return MatchResult(hit, "alias", None, 1.0)

    refs = await _fetch_axis_refs(db, axis_hint, stage_hint)

    # 2) 受控选择(LLM;dev 用确定性包含代理)
    if use_llm and refs:
        if is_llm_dev_mode():
            chosen = _controlled_select_dev(name_norm, refs)
        else:
            chosen = await _controlled_select_llm(raw_name, refs, context)
        if chosen is not None:
            return MatchResult(chosen, "controlled_llm", None, 0.9)

    # 3) 模糊兜底
    if refs:
        fz_id, ratio = _fuzzy_best(name_norm, refs)
        if fz_id is not None:
            return MatchResult(fz_id, "fuzzy", None, round(ratio, 3))

    # 4) 落候选(不建节点)
    cand_id = await _upsert_candidate(
        db, raw_name=raw_name, name_norm=name_norm, axis=axis_hint,
        stage_hint=stage_hint, source_type=source_type, source_ref=source_ref,
        context=context,
    )
    return MatchResult(None, "candidate", cand_id, 0.0)


async def match_names(
    db: AsyncSession, names: list[str], *,
    axis_hint: str = "knowledge", stage_hint: str | None = None,
    source_type: str = "uploaded_student", source_ref: dict | None = None,
    use_llm: bool = True,
) -> list[MatchResult]:
    """批量入口:一段内容抽出的知识点名列表 → 逐个受控匹配。

    R0.3 的独立可测入口(满足 §7"传一段内容→受控匹配")。
    线上抽取管线(OCR→classify_kps→本服务)的接线留到 R1。
    """
    out: list[MatchResult] = []
    for nm in names:
        out.append(await match_kp(
            db, raw_name=nm, axis_hint=axis_hint, stage_hint=stage_hint,
            source_type=source_type, source_ref=source_ref, use_llm=use_llm,
        ))
    return out
