"""R1 教材接入:单元知识点名 → 受控匹配 → unit_node 边 / 候选(带 unit 来源)。

把教材单元抽出的知识点名(AI 生成或 PDF 上传)对齐到新 knowledge_nodes:
  - 命中 → upsert unit_node 边
  - 未命中 → kp_match_service 已落候选;此处把 unit_id 追加进候选 source_ref.unit_ids,
    供 R0.4 审核 approve/merge 后自动回填单元边(见 kp_candidate_service)。
不动旧 persist_unit / unit_knowledge_points。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import CurriculumUnit, KnowledgePoint, UnitKnowledgePoint
from app.models.d15_knowledge_graph import KnowledgeNode, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_match_service import match_kp
from app.services.kp_normalize import stages_from_grades

_log = logging.getLogger(__name__)


@dataclass
class ExtractResult:
    matched: list[dict] = field(default_factory=list)     # {name, node_id, matched_by}
    candidates: list[dict] = field(default_factory=list)  # {name, candidate_id}
    edges_created: int = 0

    @property
    def stats(self) -> dict:
        return {
            "matched": len(self.matched),
            "candidate": len(self.candidates),
            "edges_created": self.edges_created,
        }


async def _upsert_unit_node(
    db: AsyncSession, unit_id: uuid.UUID, node_id: uuid.UUID, source: str
) -> bool:
    """建 unit_node 边;已存在则跳过。返回是否新建。"""
    stmt = (
        pg_insert(UnitNode)
        .values(unit_id=unit_id, node_id=node_id, source=source)
        .on_conflict_do_nothing(index_elements=["unit_id", "node_id"])
        .returning(UnitNode.unit_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _attach_unit_to_candidate(
    db: AsyncSession, candidate_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """把 unit_id 追加进候选 source_ref.unit_ids(去重),供审核后回填单元边。"""
    cand = (await db.execute(
        sa.select(KpCandidate).where(KpCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if cand is None:
        return
    ref = dict(cand.source_ref or {})
    unit_ids = list(ref.get("unit_ids", []))
    if str(unit_id) not in unit_ids:
        unit_ids.append(str(unit_id))
        ref["unit_ids"] = unit_ids
        cand.source_ref = ref
        await db.flush()


async def extract_unit_nodes(
    db: AsyncSession, *, unit_id: uuid.UUID, kp_names: list[str], source: str = "ai_extract"
) -> ExtractResult:
    """单元知识点名 → 受控匹配 → 建边/落候选。幂等(边去重,候选 occur_count 累加)。"""
    unit = (await db.execute(
        sa.select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="教材单元不存在")
    stages = stages_from_grades([unit.grade])
    stage = stages[0] if stages else None

    res = ExtractResult()
    for name in kp_names:
        if not name or not name.strip():
            continue
        r = await match_kp(
            db, raw_name=name, axis_hint="knowledge", stage_hint=stage,
            source_type="textbook",
        )
        if r.node_id is not None:
            created = await _upsert_unit_node(db, unit_id, r.node_id, source)
            res.edges_created += int(created)
            res.matched.append({"name": name, "node_id": r.node_id, "matched_by": r.matched_by})
        elif r.candidate_id is not None:
            await _attach_unit_to_candidate(db, r.candidate_id, unit_id)
            res.candidates.append({"name": name, "candidate_id": r.candidate_id})
    return res


async def extract_for_ai_unit(
    db: AsyncSession, *, unit_id: uuid.UUID, ai_unit, source: str = "ai_extract"
) -> ExtractResult | None:
    """生成流程的对齐钩子:从 AIGeneratedUnit 取 KP 名 → 受控匹配建边/候选。

    **防御式**:对齐失败只记 warning,不阻断内容生成(对齐是新增能力,不能拖垮主流程)。
    """
    try:
        names = [kp.name for kp in (getattr(ai_unit, "knowledge_points", None) or [])]
        if not names:
            return None
        res = await extract_unit_nodes(db, unit_id=unit_id, kp_names=names, source=source)
        # R5:单元 node 建好后 → 教材核心词 × 单元 node 派生 vocab_node(防御式)
        try:
            from app.services import vocab_kg_service
            await vocab_kg_service.derive_unit_vocab_nodes(db, unit_id=unit_id)
        except Exception as exc2:  # noqa: BLE001
            _log.warning("unit vocab-node derive failed (unit=%s): %s", unit_id, exc2)
        return res
    except Exception as exc:  # noqa: BLE001
        _log.warning("unit KP align failed (unit=%s): %s", unit_id, exc)
        return None


async def reextract_unit(db: AsyncSession, *, unit_id: uuid.UUID) -> ExtractResult:
    """重跑对齐:从该单元已有(旧)知识点名取材,再走受控匹配(不重新生成内容)。"""
    names = (await db.execute(
        sa.select(KnowledgePoint.name)
        .join(UnitKnowledgePoint, UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .where(UnitKnowledgePoint.unit_id == unit_id)
    )).scalars().all()
    return await extract_unit_nodes(db, unit_id=unit_id, kp_names=list(names), source="ai_extract")


async def list_unit_nodes(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """该单元的 unit_node 边(含节点名/轴/子类型/来源),供后台查看。"""
    rows = (await db.execute(
        sa.select(UnitNode.node_id, KnowledgeNode.name, KnowledgeNode.axis,
                  KnowledgeNode.node_kind, UnitNode.source)
        .join(KnowledgeNode, KnowledgeNode.id == UnitNode.node_id)
        .where(UnitNode.unit_id == unit_id)
        .order_by(UnitNode.created_at)
    )).all()
    return [
        {"node_id": nid, "name": nm, "axis": ax, "node_kind": nk, "source": src}
        for nid, nm, ax, nk, src in rows
    ]
