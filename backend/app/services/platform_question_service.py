"""R2 平台题(真题/仿真)写入与生成。

统一进 platform_question(type=real|sim),小题挂 knowledge_nodes(走 kp_match_service)。
仿真**强制有源**(parent_real_id 派生 / is_fallback 备选,DB CHECK 兜底,见 m85)。

R2.1:真题导入 import_real_question + 挂 KP(继承/匹配)骨架 + 低层 add_sim(强校验)。
R2.2/R2.3:AI 改写派生仿真 / KP 直生备选 + 真题到来下架备选。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_match_service import match_kp


@dataclass
class ImportResult:
    question_id: uuid.UUID
    matched_nodes: list[uuid.UUID] = field(default_factory=list)
    candidates: list[uuid.UUID] = field(default_factory=list)


async def attach_node(db: AsyncSession, question_id: uuid.UUID, node_id: uuid.UUID) -> bool:
    """platform_question_kp 挂边(幂等)。返回是否新建。"""
    stmt = (
        pg_insert(PlatformQuestionKp)
        .values(question_id=question_id, node_id=node_id)
        .on_conflict_do_nothing(index_elements=["question_id", "node_id"])
        .returning(PlatformQuestionKp.question_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _node_ids_of(db: AsyncSession, question_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        sa.select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == question_id)
    )).scalars().all())


async def import_real_question(
    db: AsyncSession, *,
    stem: str, answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, meta: dict | None = None,
    kp_names: list[str] | None = None, stage_hint: str | None = None,
    question_no: str | None = None, status: str = "published",
) -> ImportResult:
    """导入一道真题 → platform_question(type='real'),kp_names 走受控匹配挂 node/落候选。

    命中某 node 后调 deprecate_fallbacks_for_node:该 node 有真题了 → 其 KP 直生备选下架(决策④)。
    """
    q = PlatformQuestion(
        id=uuid.uuid4(), type="real", question_no=question_no,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, meta=meta, status=status,
    )
    db.add(q)
    await db.flush()

    res = ImportResult(question_id=q.id)
    for name in (kp_names or []):
        if not name or not name.strip():
            continue
        m = await match_kp(db, raw_name=name, axis_hint="knowledge",
                           stage_hint=stage_hint, source_type="exam")
        if m.node_id is not None:
            await attach_node(db, q.id, m.node_id)
            res.matched_nodes.append(m.node_id)
            await deprecate_fallbacks_for_node(db, node_id=m.node_id)
        elif m.candidate_id is not None:
            res.candidates.append(m.candidate_id)
    return res


async def add_sim(
    db: AsyncSession, *,
    stem: str, parent_real_id: uuid.UUID | None = None, is_fallback: bool = False,
    answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, status: str = "draft",
) -> PlatformQuestion:
    """低层仿真写入,落地铁律:必须 parent_real_id 或 is_fallback,否则拒绝(应用层先于 DB CHECK)。"""
    if parent_real_id is None and not is_fallback:
        raise AppError(code=400, message="仿真题必须有源:派生真题(parent_real_id)或显式备选(is_fallback)")
    q = PlatformQuestion(
        id=uuid.uuid4(), type="sim", parent_real_id=parent_real_id, is_fallback=is_fallback,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, status=status,
    )
    db.add(q)
    await db.flush()
    return q


async def deprecate_fallbacks_for_node(db: AsyncSession, *, node_id: uuid.UUID) -> int:
    """某 node 有真题母题后,把该 node 上的 KP 直生备选(is_fallback,未下架)置 deprecated_at。

    返回下架数量。R2.1 提供;真正有 fallback 数据在 R2.3。
    """
    rows = (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "sim",
               PlatformQuestion.is_fallback.is_(True),
               PlatformQuestion.deprecated_at.is_(None))
    )).scalars().all()
    if not rows:
        return 0
    await db.execute(
        sa.update(PlatformQuestion)
        .where(PlatformQuestion.id.in_(rows))
        .values(deprecated_at=sa.func.now(), status="retired")
    )
    return len(rows)
