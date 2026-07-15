"""学情诊断报告业务逻辑。

策略：
- 直接按 student_id 查询 wrong_questions 和 ai_analyses（无需 JOIN）。
- 内存聚合（Counter）—— MVP 阶段单用户数据量 < 1000 条，够用。
- recent_daily_activity 固定返回最近30天（含今日），无数据日期 count=0。
- top_suggestions：最近5条不重复（按 AiAnalysis.created_at 倒序）。
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import WrongRecord
from app.schemas.diagnosis import (
    DailyActivity,
    DiagnosisReport,
    ErrorTypeCount,
    KnowledgePointCount,
    KpDimensionItem,
    MasteryLedgerItem,
    SemesterDimensionItem,
)

_TOP_N = 10          # error_types / knowledge_points 取前10
_SUGGESTION_N = 5    # 最多返回5条建议
_ACTIVITY_DAYS = 30  # 近30天活跃度
# 复习建议规则已统一至 kp_mastery_service.review_suggestion（M6c 单一来源）。
# 此处保留同名薄封装，供 _build_mastery_ledger 与既有测试引用。
def _build_review_suggestion(*, accuracy: float, total: int, days_since: int | None) -> tuple[str, str]:
    """委托 kp_mastery_service.review_suggestion。"""
    from app.services import kp_mastery_service
    return kp_mastery_service.review_suggestion(
        accuracy=accuracy, total=total, days_since=days_since
    )


async def _build_mastery_ledger(
    db: AsyncSession, *, student_id: uuid.UUID
) -> list[MasteryLedgerItem]:
    """从 student_kp_mastery 台账构建带复习建议的条目列表（弱项在前）。"""
    from app.services import kp_mastery_service

    rows = await kp_mastery_service.get_mastery_tree(db, student_id=student_id)
    today = datetime.now(timezone.utc)
    items: list[MasteryLedgerItem] = []
    for r in rows:
        total = r.correct_count + r.wrong_count
        accuracy = r.correct_count / total if total > 0 else 0.0
        days_since: int | None = None
        if r.last_activity_at is not None:
            days_since = (today - r.last_activity_at.astimezone(timezone.utc)).days
        level, suggestion = _build_review_suggestion(
            accuracy=accuracy, total=total, days_since=days_since
        )
        items.append(MasteryLedgerItem(
            kp_key=r.kp_key,
            kp_id=r.kp_id,
            correct_count=r.correct_count,
            wrong_count=r.wrong_count,
            total=total,
            accuracy=round(accuracy, 4),
            level=level,
            suggestion=suggestion,
            sources=list(r.sources or []),
            last_activity_at=r.last_activity_at.isoformat() if r.last_activity_at else None,
            days_since_last=days_since,
        ))
    return items


async def get_diagnosis_report(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> DiagnosisReport:
    """聚合学生学情数据，返回诊断报告。只读，不修改数据库。"""

    # ── 1. 加载数据(统一错题中枢 wrong_record;拍照单题 AI 诊断已下线,不再读 AiAnalysis)──
    wrs_result = await db.execute(
        select(WrongRecord).where(WrongRecord.student_id == student_id)
    )
    wrs: list[WrongRecord] = list(wrs_result.scalars().all())

    # ── 2. 总览 ──────────────────────────────────────────────────────────────
    total_questions = len(wrs)
    mastered_count = sum(1 for wr in wrs if wr.status == "mastered")
    mastery_rate = round(mastered_count / total_questions, 4) if total_questions > 0 else 0.0

    total_analyzed = 0   # 旧 AI 逐题诊断已退休

    # ── 3. 薄弱知识点(按错题的归类名聚合;错误类型旧诊断退休后无来源)──────────
    error_type_counter: Counter[str] = Counter()
    kp_counter: Counter[str] = Counter()
    for wr in wrs:
        if wr.kp_name:
            kp_counter.update([wr.kp_name])

    top_error_types = [
        ErrorTypeCount(error_type=et, count=c)
        for et, c in error_type_counter.most_common(_TOP_N)
    ]
    top_weak_knowledge_points = [
        KnowledgePointCount(knowledge_point=kp, count=c)
        for kp, c in kp_counter.most_common(_TOP_N)
    ]

    # ── 4. 题型分布(wrong_record 无难度分层,留空)──────────────────────────
    question_type_distribution: dict[str, int] = {}
    difficulty_distribution: dict[int, int] = {}

    for wr in wrs:
        if wr.question_type is not None:
            question_type_distribution[wr.question_type] = (
                question_type_distribution.get(wr.question_type, 0) + 1
            )

    # ── 5. 近30天每日活跃度 ──────────────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=_ACTIVITY_DAYS - 1)

    daily_counts: dict[str, int] = {}
    for wr in wrs:
        if wr.created_at is None:
            continue
        wq_date = wr.created_at.astimezone(timezone.utc).date()
        if wq_date >= start_date:
            key = wq_date.isoformat()
            daily_counts[key] = daily_counts.get(key, 0) + 1

    recent_daily_activity = [
        DailyActivity(
            date=(start_date + timedelta(days=i)).isoformat(),
            count=daily_counts.get((start_date + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(_ACTIVITY_DAYS)
    ]

    # ── 6. 综合建议:旧逐题 AI 诊断退休,建议改由下方掌握台账/退步预警承载 ──────
    top_suggestions: list[str] = []

    # ── 7. 结构化维度：按知识点 / 按学期（来自 sim_practice_records，M3/D-094）──
    kp_dimension, semester_dimension = await _aggregate_structured_dimensions(
        db, student_id=student_id
    )

    # ── 8. 知识点掌握台账（来自 student_kp_mastery，弱项在前 + 复习建议，M6c）────
    mastery_ledger = await _build_mastery_ledger(db, student_id=student_id)

    # ── 9. 退步预警（来自 kp_mastery_snapshots 趋势对比，M13）──────────────────
    from app.services import regression_service
    regression_alerts = await regression_service.detect_regressions(db, student_id=student_id)

    return DiagnosisReport(
        total_questions=total_questions,
        total_analyzed=total_analyzed,
        mastered_count=mastered_count,
        mastery_rate=mastery_rate,
        top_error_types=top_error_types,
        top_weak_knowledge_points=top_weak_knowledge_points,
        question_type_distribution=question_type_distribution,
        difficulty_distribution=difficulty_distribution,
        recent_daily_activity=recent_daily_activity,
        top_suggestions=top_suggestions,
        kp_dimension=kp_dimension,
        semester_dimension=semester_dimension,
        mastery_ledger=mastery_ledger,
        regression_alerts=regression_alerts,
    )


async def _aggregate_structured_dimensions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> tuple[list[KpDimensionItem], list[SemesterDimensionItem]]:
    """按知识点(node) / 按学期聚合作答正确率(KP-First 数据源:answer_log,挂规范 node)。

    - 按知识点:按 answer_log.node_id 聚合,弱项(正确率低)在前。
    - 按学期:经 unit_node → curriculum_units 拿 (grade, semester);一条作答计入其 node 命中的每个学期。
    - 整卷错题的 KP 归因待整卷流写 answer_log/wrong_record 后自然纳入(整卷迁移轴),本处不再读老 user_paper KP。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import AnswerLog
    from app.models.d17_curriculum_kg import UnitNode

    recs = (await db.execute(
        select(AnswerLog.node_id, AnswerLog.is_correct)
        .where(AnswerLog.student_id == student_id, AnswerLog.node_id.isnot(None))
    )).all()

    # 按 node 聚合 [attempts, correct]
    kp_agg: dict[uuid.UUID, list[int]] = {}
    for node_id, ok in recs:
        slot = kp_agg.setdefault(node_id, [0, 0])
        slot[0] += 1
        if ok:
            slot[1] += 1

    if not kp_agg:
        return [], []

    kp_ids = list(kp_agg.keys())

    kp_meta: dict[uuid.UUID, tuple[str, str | None]] = {
        nid: (name, str(kind) if kind is not None else None)
        for nid, name, kind in (await db.execute(
            select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.node_kind)
            .where(KnowledgeNode.id.in_(kp_ids))
        )).all()
    }

    kp_dimension = [
        KpDimensionItem(
            knowledge_point_id=nid,
            knowledge_point_name=kp_meta.get(nid, ("未知知识点", None))[0],
            category=kp_meta.get(nid, (None, None))[1],
            attempts=attempts,
            correct=correct,
            accuracy=round(correct / attempts, 4) if attempts else 0.0,
        )
        for nid, (attempts, correct) in kp_agg.items()
    ]
    kp_dimension.sort(key=lambda it: (it.accuracy, -it.attempts))  # 弱项在前

    # node → {(grade, semester)} 经 unit_node → curriculum_units
    sem_map: dict[uuid.UUID, set[tuple[str, str]]] = {}
    for nid, grade, sem in (await db.execute(
        select(UnitNode.node_id, CurriculumUnit.grade, CurriculumUnit.semester)
        .join(CurriculumUnit, CurriculumUnit.id == UnitNode.unit_id)
        .where(UnitNode.node_id.in_(kp_ids))
    )).all():
        sem_map.setdefault(nid, set()).add((grade, str(sem)))

    sem_agg: dict[tuple[str, str], list[int]] = {}
    for node_id, ok in recs:
        for key in sem_map.get(node_id, set()):
            slot = sem_agg.setdefault(key, [0, 0])
            slot[0] += 1
            if ok:
                slot[1] += 1

    semester_dimension = [
        SemesterDimensionItem(
            grade=grade,
            semester=sem,
            label=f"{grade}{sem}",
            attempts=attempts,
            correct=correct,
            accuracy=round(correct / attempts, 4) if attempts else 0.0,
        )
        for (grade, sem), (attempts, correct) in sem_agg.items()
    ]
    semester_dimension.sort(key=lambda it: (it.grade, it.semester))
    return kp_dimension, semester_dimension
