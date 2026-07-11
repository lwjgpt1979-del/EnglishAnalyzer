"""个性化每日学习计划 service（M9）。

设计：无状态、无新表。每次实时从掌握台账 + 当日活动生成「今日计划」，
完成状态由真实活动派生（今日是否练过该 KP / 是否打卡），保证幂等、每日自动刷新。

任务来源（按优先级）：
1. weak_kp — 台账中正确率 < 0.7 的弱项（弱在前，最多 3 条）；done = 今日练过该 KP
2. review  — 未掌握的错题待复习；done = False（始终可操作），仅 pending>0 时出现
3. learn   — 任务过少时补一条"学习新内容"引导；done = 今日有任何练习
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import WrongQuestion
from app.models.d5_learning import StudyCheckin
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import AnswerLog
from app.schemas.learning_plan import PlanTask, TodayPlanOut
from app.services import kp_mastery_service

_MAX_WEAK_TASKS = 3
_WEAK_ACC_CEILING = 0.7  # 仅正确率 < 0.7 的 KP 进入"攻克薄弱点"


async def add_targets(db: AsyncSession, *, student_id: uuid.UUID,
                      node_ids: list[uuid.UUID], source: str = "manual") -> int:
    """把一批考点加入学生的学习目标(幂等去重)。返回新增条数。供「上传试卷→一键加入计划」。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d26_kp_target import StudentKpTarget
    added = 0
    for nid in node_ids:
        r = await db.execute(
            pg_insert(StudentKpTarget)
            .values(id=uuid.uuid4(), student_id=student_id, node_id=nid, source=source)
            .on_conflict_do_nothing(index_elements=["student_id", "node_id"])
            .returning(StudentKpTarget.id))
        if r.first() is not None:      # RETURNING 只在真插入时有行(冲突跳过则无)
            added += 1
    await db.commit()
    return added


async def _active_targets(db: AsyncSession, *, student_id: uuid.UUID, limit: int = 5) -> list[tuple]:
    """学生的学习目标里「还没掌握」的考点(未练过 或 掌握度 < 0.7)→ [(node_id, name)]。已掌握的淡出。"""
    from sqlalchemy import and_
    from app.models.d26_kp_target import StudentKpTarget
    from app.models.d16_question_domain import StudentKp
    rows = (await db.execute(
        select(StudentKpTarget.node_id, KnowledgeNode.name,
               StudentKp.fa_correct, StudentKp.fa_wrong,
               StudentKp.corrected_count, StudentKp.redo_wrong_count)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKpTarget.node_id)
        .outerjoin(StudentKp, and_(StudentKp.node_id == StudentKpTarget.node_id,
                                   StudentKp.student_id == student_id))
        .where(StudentKpTarget.student_id == student_id)
        .order_by(StudentKpTarget.created_at.desc()))).all()
    out: list[tuple] = []
    for nid, name, fac, faw, corr, redo in rows:
        if fac is None and faw is None:                 # 没练过 → 未学,保留
            out.append((nid, name))
        else:
            mastery, _ = kp_mastery_service.weighted_mastery(fac, faw, corr, redo)
            if mastery < 0.7:                           # 未掌握,保留;已掌握淡出
                out.append((nid, name))
    return out[:limit]


async def get_today_plan(db: AsyncSession, *, student_id: uuid.UUID) -> TodayPlanOut:
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)

    # 今日练过的知识点**名称**集合(KP-First:answer_log 命中 node → node 名;与台账 kp_key 按名匹配)
    practiced_names: set[str] = set(
        (await db.execute(
            select(KnowledgeNode.name)
            .join(AnswerLog, AnswerLog.node_id == KnowledgeNode.id)
            .where(AnswerLog.student_id == student_id,
                   AnswerLog.answered_at >= today_start)
        )).scalars().all()
    )
    practiced_any_today = len(practiced_names) > 0

    # 掌握台账（弱项在前）
    ledger = await kp_mastery_service.get_mastery_tree(db, student_id=student_id)

    tasks: list[PlanTask] = []
    for r in ledger:
        if len(tasks) >= _MAX_WEAK_TASKS:
            break
        total = r.correct_count + r.wrong_count
        if total == 0:
            continue
        acc = r.correct_count / total
        if acc >= _WEAK_ACC_CEILING:
            continue
        level, _suggestion = kp_mastery_service.review_suggestion(
            accuracy=acc, total=total, days_since=None
        )
        done = r.kp_key in practiced_names
        tasks.append(PlanTask(
            type="weak_kp",
            title=f"攻克薄弱点：{r.kp_key}",
            subtitle=f"正确率 {round(acc * 100)}% · 建议练 5 题",
            action="practice",
            done=done,
            kp_id=str(r.kp_id) if r.kp_id else None,
            kp_key=r.kp_key,
            accuracy=round(acc, 4),
            level=level,
        ))

    # 学习目标(上传试卷等加进来的『未学/薄弱』语法)——台账里没记录的未学考点靠它进计划;
    # 已在弱项任务里的按名去重,避免重复;已掌握的 _active_targets 已过滤淡出。
    seen_names = {t.kp_key for t in tasks if t.kp_key}
    for nid, name in await _active_targets(db, student_id=student_id):
        if name in seen_names:
            continue
        seen_names.add(name)
        tasks.append(PlanTask(
            type="learn",
            title=f"学新语法：{name}",
            subtitle="来自你上传的试卷 · 先看讲解再练",
            action="learn",
            done=name in practiced_names,
            kp_id=str(nid),
            kp_key=name,
        ))

    # 待复习错题：按 SM-2 遗忘曲线取「今日到期 + 新错题」，而非全部未掌握（M12）
    from app.services import review_service
    rstats = await review_service.get_review_stats(db, student_id=student_id)
    review_pending = int(rstats["due_today"]) + int(rstats["new_unscheduled"])
    if review_pending > 0:
        tasks.append(PlanTask(
            type="review",
            title="复习错题",
            subtitle=f"今日待复习 {review_pending} 道（遗忘曲线）",
            action="review",
            done=False,
            count=review_pending,
        ))

    # 任务过少时补"学习新内容"引导
    if len(tasks) < 2:
        tasks.append(PlanTask(
            type="learn",
            title="学习新内容",
            subtitle="继续按教材学习知识点",
            action="learn",
            done=practiced_any_today,
        ))

    # 今日打卡状态
    checkin_done = (await db.execute(
        select(StudyCheckin.id).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date == today,
        )
    )).first() is not None

    completed = sum(1 for t in tasks if t.done)
    return TodayPlanOut(
        date=str(today),
        tasks=tasks,
        completed_count=completed,
        total_count=len(tasks),
        checkin_done=checkin_done,
        review_pending=review_pending,
    )
