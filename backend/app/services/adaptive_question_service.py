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
# 物化时可继承的题型(须 ∈ ai_question_type_enum)
_MATERIALIZE_ENUM_TYPES = {"单选", "填空", "完型", "阅读", "写作", "判断", "连线"}
# 客观填空类(无选项但答案可字符串判分)——物化时映射成 enum「填空」进练习流。
# 主观自由作答(阅读表达/写作)不在此列:走独立 LLM 批改,不进字符串判分练习。
_FILL_TYPES = {"动词填空", "词汇运用", "填空", "短文填空", "单词检测", "选词填空"}


def _to_enum_type(qt: str | None) -> str:
    """平台题型 → SimulatedQuestion.question_type(ai_question_type_enum 合法值)。"""
    if qt in _FILL_TYPES:
        return "填空"
    return qt if qt in _MATERIALIZE_ENUM_TYPES else "单选"


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


async def _materialize_sims_from_platform(db: AsyncSession, *, kp) -> int:
    """把该 KP 对应 node 的已发布·有内容 platform 仿真物化进 SimulatedQuestion(kp 维度,判分链复用)。

    按源 PQ id 去重(generation_metadata.source_platform_question_id)。返回新建数。无 node/无有源题→0。
    """
    from app.services.kp_match_service import match_kp
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp, Passage

    m = await match_kp(db, raw_name=kp.name, axis_hint="knowledge", source_type="exam", use_llm=False)
    if m.node_id is None:
        return 0
    rows = (await db.execute(
        select(PlatformQuestion)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == m.node_id,
               PlatformQuestion.type == "sim",
               PlatformQuestion.status == "published",
               PlatformQuestion.deprecated_at.is_(None),
               PlatformQuestion.answer.isnot(None),
               # 选择题(有选项)或客观填空类(动词填空/词汇运用等)都可进练习字符串判分;
               # 主观自由作答(阅读表达无选项的「阅读」/写作)排除,走独立 LLM 批改。
               sa.or_(PlatformQuestion.options.isnot(None),
                      PlatformQuestion.question_type.in_(_FILL_TYPES)))
        .limit(_PER_KP)
    )).scalars().all()
    # 批量取题组短文(block_id→Passage.text),让完型/阅读微题物化后仍带上下文（P1）
    block_ids = {pq.block_id for pq in rows if pq.block_id}
    passage_map: dict = {}
    if block_ids:
        passage_map = {pid: txt for pid, txt in (await db.execute(
            select(Passage.id, Passage.text).where(Passage.id.in_(block_ids)))).all()}
    created = 0
    for pq in rows:
        exists = (await db.execute(
            select(SimulatedQuestion.id).where(
                SimulatedQuestion.generation_metadata["source_platform_question_id"].astext == str(pq.id))
        )).scalar_one_or_none()
        if exists is not None:
            continue
        meta = {"source_platform_question_id": str(pq.id)}
        pg = passage_map.get(pq.block_id) if pq.block_id else None
        if pg:
            meta["passage"] = pg
        # 如实继承题型(完型/阅读不压成单选;动词填空/词汇运用等客观填空 → enum「填空」)
        qt = _to_enum_type(pq.question_type)
        db.add(SimulatedQuestion(
            id=uuid.uuid4(), source_exam_question_id=None, knowledge_point_id=kp.id,
            question_type=qt, stem=pq.stem, options=pq.options, answer=pq.answer,
            explanation=pq.explanation, difficulty=(pq.difficulty or 3), status="published",
            generation_metadata=meta))
        created += 1
    if created:
        await db.flush()
    return created


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

        # R7 收尾:取材优先 platform_question 有源题 → 物化进 SimulatedQuestion(判分链不变),
        # 被下面 existing 选中后即跳过 AI 生成;无有源题则照旧 AI 兜底。
        await _materialize_sims_from_platform(db, kp=kp)

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
