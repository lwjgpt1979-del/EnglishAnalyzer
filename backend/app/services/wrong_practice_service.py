"""R3 有源练同类(KP-First 铁律落地):错题 → node → 真题派生仿真 / 无真题则 KP 直生备选。

替换旧 AI 直生(practice_service.generate_practice_questions → ai_questions,无源)。
所有产出都是 platform_question 的 sim(parent_real_id 派生 或 is_fallback 备选),必有源。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services import platform_question_service as pqs


@dataclass
class SameKindResult:
    node_id: uuid.UUID
    real_id: uuid.UUID | None       # 母题真题(无真题时 None)
    sim_ids: list[uuid.UUID]        # 供练习的仿真(派生或备选)
    fallback: bool                  # 是否走了 KP 直生备选(无真题)


async def _real_for_node(db: AsyncSession, node_id: uuid.UUID) -> uuid.UUID | None:
    return (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "real", PlatformQuestion.status == "published")
        .limit(1)
    )).scalar_one_or_none()


async def _node_sims(db: AsyncSession, node_id: uuid.UUID, limit: int) -> list[uuid.UUID]:
    """该 node 现有可用仿真(未下架)。"""
    return list((await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "sim",
               PlatformQuestion.deprecated_at.is_(None))
        .order_by(PlatformQuestion.created_at).limit(limit)
    )).scalars().all())


async def practice_same_kind(
    db: AsyncSession, *, node_id: uuid.UUID, count: int = 3
) -> SameKindResult:
    """为某 KP 取 count 道有源仿真:优先复用现有,不足则按需补(真题派生 / 无真题则备选)。"""
    real_id = await _real_for_node(db, node_id)
    existing = await _node_sims(db, node_id, count)
    if len(existing) < count:
        need = count - len(existing)
        if real_id is not None:
            await pqs.generate_sim_from_real(db, real_id=real_id, count=need)
        else:
            await pqs.generate_fallback_sim(db, node_id=node_id, count=need)
        existing = await _node_sims(db, node_id, count)
    return SameKindResult(
        node_id=node_id, real_id=real_id, sim_ids=existing[:count],
        fallback=real_id is None,
    )
