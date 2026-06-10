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

from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
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

    # ── 1. 加载数据 ──────────────────────────────────────────────────────────
    wqs_result = await db.execute(
        select(WrongQuestion).where(WrongQuestion.student_id == student_id)
    )
    wqs: list[WrongQuestion] = list(wqs_result.scalars().all())

    analyses_result = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.student_id == student_id)
        .order_by(AiAnalysis.created_at.desc())
    )
    analyses: list[AiAnalysis] = list(analyses_result.scalars().all())

    # ── 2. 总览 ──────────────────────────────────────────────────────────────
    total_questions = len(wqs)
    mastered_count = sum(1 for wq in wqs if wq.is_mastered)
    mastery_rate = round(mastered_count / total_questions, 4) if total_questions > 0 else 0.0

    analyzed_wq_ids = {a.wrong_question_id for a in analyses}
    total_analyzed = len(analyzed_wq_ids)

    # ── 3. 错误类型 & 知识点（Counter 聚合）──────────────────────────────────
    error_type_counter: Counter[str] = Counter()
    kp_counter: Counter[str] = Counter()

    for a in analyses:
        if a.error_types:
            error_type_counter.update(a.error_types)
        if a.knowledge_points:
            kp_counter.update(a.knowledge_points)

    top_error_types = [
        ErrorTypeCount(error_type=et, count=c)
        for et, c in error_type_counter.most_common(_TOP_N)
    ]
    top_weak_knowledge_points = [
        KnowledgePointCount(knowledge_point=kp, count=c)
        for kp, c in kp_counter.most_common(_TOP_N)
    ]

    # ── 4. 题型 & 难度分布 ────────────────────────────────────────────────────
    question_type_distribution: dict[str, int] = {}
    difficulty_distribution: dict[int, int] = {}

    for wq in wqs:
        if wq.question_type is not None:
            question_type_distribution[wq.question_type] = (
                question_type_distribution.get(wq.question_type, 0) + 1
            )
        if wq.difficulty is not None:
            difficulty_distribution[wq.difficulty] = (
                difficulty_distribution.get(wq.difficulty, 0) + 1
            )

    # ── 5. 近30天每日活跃度 ──────────────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=_ACTIVITY_DAYS - 1)

    daily_counts: dict[str, int] = {}
    for wq in wqs:
        wq_date = wq.created_at.astimezone(timezone.utc).date()
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

    # ── 6. 综合建议（最近5条不重复）─────────────────────────────────────────
    seen_suggestions: set[str] = set()
    top_suggestions: list[str] = []
    for a in analyses:                           # 已按 created_at DESC 排序
        s = (a.suggestions or "").strip()
        if s and s not in seen_suggestions:
            seen_suggestions.add(s)
            top_suggestions.append(s)
        if len(top_suggestions) >= _SUGGESTION_N:
            break

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
    """按知识点 / 按学期聚合练习正确率（数据源：sim_practice_records）。

    - 按知识点：直接按 knowledge_point_id 聚合，弱项（正确率低）在前。
    - 按学期：经 unit_knowledge_points → curriculum_units 拿到 (grade, semester)；
      一条作答记录计入其知识点命中的每个学期，同一学期内去重（避免同学期多单元重复计数）。
    """
    from app.models.d4_knowledge import (
        CurriculumUnit,
        KnowledgePoint,
        UnitKnowledgePoint,
    )
    from app.models.d12_v2_exams import SimPracticeRecord

    recs = (await db.execute(
        select(SimPracticeRecord.knowledge_point_id, SimPracticeRecord.is_correct)
        .where(SimPracticeRecord.student_id == student_id)
    )).all()

    # 按 KP 聚合 [attempts, correct]（来源：sim_practice_records）
    kp_agg: dict[uuid.UUID, list[int]] = {}
    for kp_id, ok in recs:
        slot = kp_agg.setdefault(kp_id, [0, 0])
        slot[0] += 1
        if ok:
            slot[1] += 1

    # ── 整卷错题 KP（来源：user_paper_question_knowledge_points，is_wrong=True）──
    from app.models.d13_v2_user_papers import (
        UserPaperQuestion,
        UserPaperQuestionKnowledgePoint,
        UserUploadedPaper,
    )
    paper_kp_ids = (await db.execute(
        select(UserPaperQuestionKnowledgePoint.knowledge_point_id)
        .join(
            UserPaperQuestion,
            UserPaperQuestion.id == UserPaperQuestionKnowledgePoint.user_paper_question_id,
        )
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(
            UserUploadedPaper.student_id == student_id,
            UserPaperQuestion.is_wrong == True,
        )
    )).scalars().all()
    for kp_id in paper_kp_ids:
        slot = kp_agg.setdefault(kp_id, [0, 0])
        slot[0] += 1          # attempt + 1
        # is_correct = False（is_wrong=True → 不加 correct）

    if not kp_agg:
        return [], []

    kp_ids = list(kp_agg.keys())

    kp_meta: dict[uuid.UUID, tuple[str, str | None]] = {
        kid: (name, str(cat) if cat is not None else None)
        for kid, name, cat in (await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.category)
            .where(KnowledgePoint.id.in_(kp_ids))
        )).all()
    }

    kp_dimension = [
        KpDimensionItem(
            knowledge_point_id=kid,
            knowledge_point_name=kp_meta.get(kid, ("未知知识点", None))[0],
            category=kp_meta.get(kid, (None, None))[1],
            attempts=attempts,
            correct=correct,
            accuracy=round(correct / attempts, 4) if attempts else 0.0,
        )
        for kid, (attempts, correct) in kp_agg.items()
    ]
    kp_dimension.sort(key=lambda it: (it.accuracy, -it.attempts))  # 弱项在前

    # KP → {(grade, semester)}
    sem_map: dict[uuid.UUID, set[tuple[str, str]]] = {}
    for kid, grade, sem in (await db.execute(
        select(
            UnitKnowledgePoint.knowledge_point_id,
            CurriculumUnit.grade,
            CurriculumUnit.semester,
        )
        .join(CurriculumUnit, CurriculumUnit.id == UnitKnowledgePoint.unit_id)
        .where(UnitKnowledgePoint.knowledge_point_id.in_(kp_ids))
    )).all():
        sem_map.setdefault(kid, set()).add((grade, str(sem)))

    sem_agg: dict[tuple[str, str], list[int]] = {}
    for kp_id, ok in recs:
        for key in sem_map.get(kp_id, set()):
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
