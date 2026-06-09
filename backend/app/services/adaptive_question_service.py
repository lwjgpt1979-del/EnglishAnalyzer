"""按薄弱知识点智能组卷（D-130 AI 智能出题）。

算法（M43 升级）：
1. 优先从 student_kp_mastery 台账中取正确率最低的 TOP_KPS 个 KP（有答题记录）
2. 台账为空时 fallback：从 ai_analyses 聚合薄弱知识点名称（向后兼容）
3. 按名称反查 knowledge_points 表拿到 KP 对象（只取已存在的）
4. 对每个 KP：从 simulated_questions 取 published 且该学生未做过的题
5. 不足总量时调 question_ai_service 生成新题并以 published 状态入库
6. 返回按难度升序排列的题集，不超过 total 道
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis
from app.models.d4_knowledge import KnowledgePoint
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
    from app.models.d4_knowledge import StudentKpMastery
    import sqlalchemy as sa

    rows = list(
        (await db.execute(
            select(StudentKpMastery).where(
                StudentKpMastery.student_id == student_id,
                (StudentKpMastery.correct_count + StudentKpMastery.wrong_count) > 0,
            ).order_by(
                sa.case(
                    (StudentKpMastery.correct_count + StudentKpMastery.wrong_count == 0, 1),
                    else_=0,
                ),
                sa.case(
                    ((StudentKpMastery.correct_count + StudentKpMastery.wrong_count) > 0,
                     sa.cast(StudentKpMastery.correct_count, sa.Float)
                     / (StudentKpMastery.correct_count + StudentKpMastery.wrong_count)),
                    else_=sa.literal(0.0),
                ).asc(),
                StudentKpMastery.last_activity_at.desc().nulls_last(),
            ).limit(top_n)
        )).scalars().all()
    )
    return [r.kp_key for r in rows]


async def get_adaptive_set(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    total: int = _DEFAULT_TOTAL,
) -> AdaptiveSet:
    # ── 1. M43：优先从台账读弱项，fallback 到 ai_analyses ────────────────
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

    # ── 2. 反查 KP 对象 ────────────────────────────────────────────────────
    kp_rows = list(
        (await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.name.in_(top_kp_names))
        )).scalars().all()
    )

    if not kp_rows:
        return AdaptiveSet(weak_kp_names=top_kp_names)

    # ── 3. 查已做过的题 ID ─────────────────────────────────────────────────
    done_ids: set[uuid.UUID] = set(
        (await db.execute(
            select(SimPracticeRecord.simulated_question_id).where(
                SimPracticeRecord.student_id == student_id
            )
        )).scalars().all()
    )

    # ── 4. 取题 + 必要时 AI 补充 ───────────────────────────────────────────
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

    # ── 5. 截断 + 按难度升序 ───────────────────────────────────────────────
    collected = collected[:total]
    collected.sort(key=lambda q: q.difficulty)

    return AdaptiveSet(questions=collected, weak_kp_names=top_kp_names)
