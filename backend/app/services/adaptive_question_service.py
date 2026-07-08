"""按薄弱知识点智能组卷(KP-First:弱项取自 student_kp/answer_log,出题走 question_serve_service)。

彻底退出老 simulated_questions:
- 弱 node 选取:全局=student_kp 正确率最低(有练习记录);单元=unit_node 里未练习/最弱在前。
- 出题:question_serve_service.serve_by_node(platform 仿真优先→LLM 兜底,默认上架),排除已做题(answer_log)。
- 不再物化 simulated_questions、不再读 sim_practice_records;去重真值 = answer_log(q_scope=platform)。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import AnswerLog, StudentKp
from app.models.d17_curriculum_kg import UnitNode
from app.schemas.questions import SimQuestionOut
from app.services import question_serve_service

_TOP_KPS = 3        # 最多取前 3 个薄弱 node
_PER_KP = 5         # 每个 node 最多取几道题
_DEFAULT_TOTAL = 5  # 默认总题数


@dataclass
class AdaptiveSet:
    questions: list[SimQuestionOut] = field(default_factory=list)
    weak_kp_names: list[str] = field(default_factory=list)


def _accuracy_expr():
    """正确率 = (练习数-错数)/练习数;练习数为 0 时取 0(视为最弱)。"""
    return sa.case(
        (StudentKp.practice_count > 0,
         sa.cast(StudentKp.practice_count - StudentKp.wrong_count, sa.Float)
         / sa.cast(StudentKp.practice_count, sa.Float)),
        else_=0.0,
    )


async def _weak_nodes_global(
    db: AsyncSession, *, student_id: uuid.UUID, top_n: int,
) -> list[tuple[uuid.UUID, str]]:
    """全局弱项:student_kp 里有练习记录、正确率最低的 node 在前。"""
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name)
        .join(StudentKp, StudentKp.node_id == KnowledgeNode.id)
        .where(StudentKp.student_id == student_id,
               StudentKp.practice_count > 0,
               StudentKp.in_scope.is_(True))
        .order_by(_accuracy_expr().asc(), StudentKp.last_practice_at.asc().nulls_first())
        .limit(top_n))).all()
    return [(r.id, r.name) for r in rows]


async def _weak_nodes_unit(
    db: AsyncSession, *, student_id: uuid.UUID, unit_id: uuid.UUID, top_n: int,
) -> list[tuple[uuid.UUID, str]]:
    """单元维度:unit_node 的 node LEFT JOIN student_kp,未练习(正确率 0)/最弱在前。"""
    acc = sa.func.coalesce(_accuracy_expr(), 0.0)
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .outerjoin(StudentKp, sa.and_(
            StudentKp.node_id == KnowledgeNode.id, StudentKp.student_id == student_id))
        .where(UnitNode.unit_id == unit_id)
        .order_by(acc.asc(), StudentKp.last_practice_at.asc().nulls_first())
        .limit(top_n))).all()
    return [(r.id, r.name) for r in rows]


async def _done_platform_ids(db: AsyncSession, student_id: uuid.UUID) -> set[uuid.UUID]:
    """已做过的平台题(answer_log 真值),自适应去重用。"""
    return set((await db.execute(
        sa.select(AnswerLog.question_id).where(
            AnswerLog.student_id == student_id, AnswerLog.q_scope == "platform"))).scalars().all())


async def get_adaptive_set(
    db: AsyncSession, *, student_id: uuid.UUID,
    total: int = _DEFAULT_TOTAL, unit_id: Optional[uuid.UUID] = None,
) -> AdaptiveSet:
    weak = (await _weak_nodes_unit(db, student_id=student_id, unit_id=unit_id, top_n=_TOP_KPS)
            if unit_id is not None
            else await _weak_nodes_global(db, student_id=student_id, top_n=_TOP_KPS))
    if not weak:
        return AdaptiveSet()

    done = await _done_platform_ids(db, student_id)
    collected: list[SimQuestionOut] = []
    for node_id, _name in weak:
        if len(collected) >= total:
            break
        need = min(_PER_KP, total - len(collected))
        qs = await question_serve_service.serve_by_node(
            db, node_id=node_id, count=need, exclude_ids=done)
        collected.extend(qs)
        done.update(q.id for q in qs)     # 跨 node 也不重复

    collected = collected[:total]
    collected.sort(key=lambda q: q.difficulty)
    return AdaptiveSet(questions=collected, weak_kp_names=[n for _, n in weak])
