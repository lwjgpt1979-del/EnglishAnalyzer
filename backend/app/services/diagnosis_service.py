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
)

_TOP_N = 10          # error_types / knowledge_points 取前10
_SUGGESTION_N = 5    # 最多返回5条建议
_ACTIVITY_DAYS = 30  # 近30天活跃度


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
    )
