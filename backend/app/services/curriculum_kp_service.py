"""R1 教材接入:单元知识点名 → 受控匹配 → unit_node 边 / 候选(带 unit 来源)。

把教材单元抽出的知识点名(AI 生成或 PDF 上传)对齐到新 knowledge_nodes:
  - 命中 → upsert unit_node 边
  - 未命中 → kp_match_service 已落候选;此处把 unit_id 追加进候选 source_ref.unit_ids,
    供 R0.4 审核 approve/merge 后自动回填单元边(见 kp_candidate_service)。
不动旧 persist_unit / unit_knowledge_points。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_match_service import match_kp
from app.services.kp_normalize import stages_from_grades


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
