"""按薄弱知识点智能组卷（D-130 AI 智能出题）。

算法（M6 升级 — 单元维度 + 未练习兜底）：

模式 A — 全局弱项（无 unit_id）：
1. 优先从 student_kp_mastery 台账中取正确率最低的 TOP_KPS 个 KP（有答题记录）
2. 台账为空时 fallback：从 ai_analyses 聚合薄弱知识点名称（向后兼容）
3. 按名称反查 knowledge_points 拿到 KP 对象，取题/AI 补题

模式 B — 单元维度（有 unit_id）：
1. 取该单元所有 KP（unit_knowledge_points JOIN knowledge_points）
2. LEFT JOIN student_kp_mastery 得到每个 KP 的正确率（无记录 = 未练习 → accuracy 视为 0）
3. 按 accuracy ASC（未练习最优先）→ last_activity_at ASC（越久没练越优先）排序
4. 取 TOP_KPS 个弱项 KP，取题/AI 补题
5. 返回按难度升序的题集
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis
from app.models.d4_knowledge import KnowledgePoint, StudentKpMastery, UnitKnowledgePoint
from app.models.d12_v2_exams import SimPracticeRecord, SimulatedQuestion
from app.services import question_service
from app.services.question_ai_service import generate_questions

_TOP_KPS = 3        # 最多取前3个薄弱知识点
_PER_KP = 5         # 每个知识点最多取几道题
_DEFAULT_TOTAL = 5  # 默认总题数


@dataclass
class AdaptiveSet:
    questions: list[SimulatedQuestion] = field(default_factory=list)
    weak_kp_names: list[str] = field(default_factory=list)


async def _get_weak_kp_names_from_mastery(
    db: AsyncSession, *, student_id: uuid.UUID, top_n: int = _TOP_KPS
) -> list[str]:
    """从 student_kp_mastery 台账取正确率最低的 KP 名称（有答题记录优先）。

    排序：有答题记录 → accuracy ASC → last_activity_at DESC
    只取有实际答题次数的记录（correct+wrong > 0）。
    """
    rows = list(
        (await db.execute(
            select(StudentKpMastery).where(
                StudentKpMastery.student_id == student_id,
                StudentKpMastery.last_activity_at.is_not(None),
            ).order_by(
                (
                    sa.cast(StudentKpMastery.correct_count, sa.Float)
                    / (StudentKpMastery.correct_count + StudentKpMastery.wrong_count)
                ).asc(),
                StudentKpMastery.last_activity_at.desc().nulls_last(),
            ).limit(top_n)
        )).scalars().all()
    )
    return [r.kp_key for r in rows]


async def _get_weak_kps_for_unit(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    unit_id: uuid.UUID,
    top_n: int = _TOP_KPS,
) -> list[KnowledgePoint]:
    """单元维度弱项选取：

    - 取该单元所有 KP
    - LEFT JOIN student_kp_mastery，未练习的视为 accuracy=0（最弱）
    - 排序：accuracy ASC（0=未练习最优先），last_activity_at ASC nulls_first
    - 返回 KnowledgePoint 对象列表
    """
    # 子查询：该学生对每个 kp_key 的正确率
    mastery_sq = (
        select(
            StudentKpMastery.kp_key,
            (
                sa.cast(StudentKpMastery.correct_count, sa.Float)
                / (StudentKpMastery.correct_count + StudentKpMastery.wrong_count)
            ).label("accuracy"),
            StudentKpMastery.last_activity_at,
        )
        .where(StudentKpMastery.student_id == student_id)
        .subquery()
    )

    rows = (await db.execute(
        select(
            KnowledgePoint,
            sa.func.coalesce(mastery_sq.c.accuracy, 0.0).label("accuracy"),
            mastery_sq.c.last_activity_at,
        )
        .join(UnitKnowledgePoint, UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .outerjoin(mastery_sq, mastery_sq.c.kp_key == KnowledgePoint.name)
        .where(UnitKnowledgePoint.unit_id == unit_id)
        .order_by(
            sa.func.coalesce(mastery_sq.c.accuracy, 0.0).asc(),
            mastery_sq.c.last_activity_at.asc().nulls_first(),
        )
        .limit(top_n)
    )).all()

    return [row[0] for row in rows]


async def get_adaptive_set(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    total: int = _DEFAULT_TOTAL,
    unit_id: Optional[uuid.UUID] = None,
) -> AdaptiveSet:
    # ── 获取目标 KP 对象列表 ───────────────────────────────────────────────
    if unit_id is not None:
        # 模式 B：单元维度，未练习 KP 排最前
        kp_rows = await _get_weak_kps_for_unit(
            db, student_id=student_id, unit_id=unit_id, top_n=_TOP_KPS
        )
        if not kp_rows:
            return AdaptiveSet()
        top_kp_names = [kp.name for kp in kp_rows]
    else:
        # 模式 A：全局弱项
        top_kp_names = await _get_weak_kp_names_from_mastery(db, student_id=student_id)

        if not top_kp_names:
            # fallback：从 ai_analyses 聚合（向后兼容旧逻辑）
            analyses = list(
                (await db.execute(
                    select(AiAnalysis).where(AiAnalysis.student_id == student_id)
                )).scalars().all()
            )
            kp_counter: Counter[str] = Counter()
            for a in analyses:
                if a.knowledge_points:
                    kp_counter.update(a.knowledge_points)
            if not kp_counter:
                return AdaptiveSet()
            top_kp_names = [name for name, _ in kp_counter.most_common(_TOP_KPS)]

        kp_rows = list(
            (await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.name.in_(top_kp_names))
            )).scalars().all()
        )
        if not kp_rows:
            return AdaptiveSet(weak_kp_names=top_kp_names)

    # ── 查已做过的题 ID ─────────────────────────────────────────────────
    done_ids: set[uuid.UUID] = set(
        (await db.execute(
            select(SimPracticeRecord.simulated_question_id).where(
                SimPracticeRecord.student_id == student_id
            )
        )).scalars().all()
    )

    # ── 取题 + 必要时 AI 补充 ───────────────────────────────────────────
    collected: list[SimulatedQuestion] = []

    for kp in kp_rows:
        if len(collected) >= total:
            break

        # 查 published 且未做过的题
        existing = list(
            (await db.execute(
                select(SimulatedQuestion).where(
                    SimulatedQuestion.knowledge_point_id == kp.id,
                    SimulatedQuestion.status == "published",
                    SimulatedQuestion.id.not_in(done_ids) if done_ids else True,
                ).limit(_PER_KP)
            )).scalars().all()
        )

        # 不足时 AI 生成新题补充
        if len(existing) < 2:
            ai_qs = await generate_questions(
                kp_name=kp.name,
                kp_category=kp.category,
                kp_description=kp.description,
                count=3,
            )
            new_saved = await question_service.persist_questions(
                db, kp_id=kp.id, questions=ai_qs, status="published"
            )
            await db.flush()
            # 过滤掉已做过的
            new_unseen = [q for q in new_saved if q.id not in done_ids]
            existing = (existing + new_unseen)[:_PER_KP]

        collected.extend(existing)

    # ── 截断 + 按难度升序 ───────────────────────────────────────────────
    collected = collected[:total]
    collected.sort(key=lambda q: q.difficulty)

    return AdaptiveSet(questions=collected, weak_kp_names=top_kp_names)
