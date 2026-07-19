"""个性化每日学习计划 service（M9）。

设计：无状态、无新表。每次实时从掌握台账 + 当日活动生成「今日计划」，
完成状态由真实活动派生（今日是否练过该 KP / 是否打卡），保证幂等、每日自动刷新。

任务来源（按优先级）：
1. weak_kp — 台账中正确率 < 0.7 的弱项（弱在前，最多 3 条）；done = 今日练过该 KP
2. review  — 未掌握的错题待复习；done = False（始终可操作），仅 pending>0 时出现
3. learn   — 任务过少时补一条"学习新内容"引导；done = 今日有任何练习
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudyCheckin
from app.models.d9_system import SystemConfig
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import AnswerLog
from app.schemas.learning_plan import TodayPlanOut
from app.services import kp_mastery_service

_MAX_WEAK_TASKS = 3
_WEAK_ACC_CEILING = 0.7  # 仅正确率 < 0.7 的 KP 进入"攻克薄弱点"

# ── 课程精讲「每日上限」(运营可配置 · system_configs)─────────────────────────────
# 今日计划课程格 count = min(当前单元剩余, 每日上限);作业格不封顶(应尽快清完)。
# 本常量仅作缺配置时的兜底默认,实际值见 get_daily_caps()/后台配置页。
_DAILY_CAPS_KEY = "learning_plan_daily_caps"
_DEFAULT_DAILY_CAPS: dict[str, int] = {"word": 10, "grammar": 3, "sentence": 3}


async def get_daily_caps(db: AsyncSession) -> dict[str, int]:
    """读 system_configs.learning_plan_daily_caps(课程每日上限,条/天)。缺失/越界回落默认。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _DAILY_CAPS_KEY))).scalar_one_or_none()
    if cfg is None:
        return dict(_DEFAULT_DAILY_CAPS)
    data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    out = dict(_DEFAULT_DAILY_CAPS)
    for k in out:
        try:
            v = int(data.get(k, out[k]))
            if v > 0:
                out[k] = v
        except (TypeError, ValueError):
            pass
    return out


async def update_daily_caps(db: AsyncSession, *, caps: dict, updated_by: uuid.UUID) -> dict[str, int]:
    """运营改课程每日上限:upsert system_configs.learning_plan_daily_caps(key 唯一)。仅收白名单键、正整数。"""
    merged = dict(_DEFAULT_DAILY_CAPS)
    for k in merged:
        try:
            v = int(caps.get(k, merged[k]))
            if v > 0:
                merged[k] = v
        except (TypeError, ValueError):
            pass
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _DAILY_CAPS_KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_DAILY_CAPS_KEY, value=merged,
            description="今日学习计划·课程每日上限(word/grammar/sentence,条/天)",
            updated_by=updated_by))
    else:
        cfg.value = merged
        cfg.updated_by = updated_by
    await db.flush()
    return merged


async def add_targets(db: AsyncSession, *, student_id: uuid.UUID,
                      node_ids: list[uuid.UUID], source: str = "manual",
                      source_paper_id: uuid.UUID | None = None) -> int:
    """把一批考点加入学生的学习目标(幂等去重)。返回新增条数。供「上传试卷→一键加入计划」。
    source_paper_id:来源卷(作业精讲按批次归组)。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d26_kp_target import StudentKpTarget
    added = 0
    for nid in node_ids:
        r = await db.execute(
            pg_insert(StudentKpTarget)
            .values(id=uuid.uuid4(), student_id=student_id, node_id=nid,
                    source=source, source_paper_id=source_paper_id)
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


def _sum_batches(batches: list[dict], total_key: str) -> tuple[int, int]:
    """按批次汇总 (total, studied)。total_key 因模块而异(单词=word_count,其余=count)。"""
    total = sum(int(b.get(total_key, 0)) for b in batches)
    studied = sum(int(b.get("studied", 0)) for b in batches)
    return total, studied


def _current_unit(units: list[dict]) -> dict | None:
    """课程精讲当前聚焦单元:第一关「已解锁且未学完」;全学完/无解锁则取最后一单元。"""
    for u in units:
        if (u.get("total") or 0) > 0 and (u.get("studied") or 0) < u["total"] and u.get("unlocked", True):
            return u
    return units[-1] if units else None


async def get_today_plan(db: AsyncSession, *, student_id: uuid.UUID) -> TodayPlanOut:
    """今日学习计划:两来源(作业精讲 / 课程精讲)× 各模块今日待做 + 今日复习(仅错题)。
    数字/进度复用各精讲模块既有 studied 口径(homework_batches / course_units),不新造数据。"""
    from app.schemas.learning_plan import PlanReview, PlanSource, PlanTile
    from app.services import (
        grammar_intensive_service as gis,
        reading_intensive_service as ris,
        sentence_intensive_service as sis,
        vocab_intensive_service as vis,
        wrong_review_service,
    )
    today = datetime.now(timezone.utc).date()

    # ── 作业精讲:四模块按批次(卷)汇总 total/studied ──
    hw_defs = [
        ("word", "单词", "word_count", "/pages/intensive/words?mode=homework",
         await vis.homework_batches(db, student_id=student_id)),
        ("grammar", "语法", "count", "/pages/intensive/grammar?mode=homework",
         await gis.homework_batches(db, student_id=student_id)),
        ("sentence", "长难句", "count", "/pages/intensive/sentence?mode=homework",
         await sis.homework_batches(db, student_id=student_id)),
        ("reading", "阅读", "count", "/pages/intensive/reading?mode=homework",
         await ris.homework_batches(db, student_id=student_id)),
    ]
    hw_tiles = []
    for mod, title, key, route, batches in hw_defs:
        total, studied = _sum_batches(batches, key)
        hw_tiles.append(PlanTile(module=mod, title=title, count=max(0, total - studied),
                                 studied=studied, total=total, route=route))

    # ── 课程精讲:三模块按当前教材单元,count 按每日上限封顶(单元剩余 = total-studied)──
    caps = await get_daily_caps(db)

    def _course_tile(mod: str, title: str, route: str, data: dict) -> "PlanTile":
        cur = _current_unit(data.get("units") or [])
        total = int(cur.get("total") or 0) if cur else 0
        studied = int(cur.get("studied") or 0) if cur else 0
        remaining = max(0, total - studied)
        cap = caps.get(mod) or remaining
        return PlanTile(module=mod, title=title, count=min(remaining, cap),
                        studied=studied, total=total, route=route)

    vc = await vis.course_units(db, student_id=student_id)
    gc = await gis.course_units(db, student_id=student_id)
    sc = await sis.course_units(db, student_id=student_id)
    course_tiles = [
        _course_tile("word", "单词", "/pages/intensive/words?mode=course", vc),
        _course_tile("grammar", "语法", "/pages/intensive/grammar?mode=course", gc),
        _course_tile("sentence", "长难句", "/pages/intensive/sentence?mode=course", sc),
    ]
    g, s = vc.get("grade"), vc.get("semester")
    course_sub = f"{g}{s}册" if (g and s) else "按教材学"

    # ── 今日复习:仅错题(遗忘曲线;词/句后续再并)──
    rstats = await wrong_review_service.review_stats(db, student_id=student_id)
    review_count = int(rstats["due_today"]) + int(rstats["new_unscheduled"])
    review = PlanReview(
        count=review_count,
        subtitle=f"错题 {review_count} 道 · 遗忘曲线" if review_count else "今日无到期错题",
        route="/pages/wrong-questions/review")

    sources = [
        PlanSource(source="homework", title="作业精讲", subtitle="优先", available=True, tiles=hw_tiles),
        PlanSource(source="course", title="课程精讲", subtitle=course_sub,
                   available=bool(vc.get("version")), tiles=course_tiles),
    ]

    # 进度:有内容的模块格(total>0)里已学完的比例;复习不计入分母
    graded = [t for t in hw_tiles + course_tiles if t.total > 0]
    total_count = len(graded) + (1 if review_count > 0 else 0)
    completed_count = sum(1 for t in graded if t.studied >= t.total)

    checkin_done = (await db.execute(
        select(StudyCheckin.id).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date == today,
        )
    )).first() is not None

    return TodayPlanOut(
        date=str(today), sources=sources, review=review,
        completed_count=completed_count, total_count=total_count,
        checkin_done=checkin_done, review_pending=review_count,
    )
