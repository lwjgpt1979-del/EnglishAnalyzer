"""学情退步预警 service（M13）。

检测「知识点正确率下滑」：对每个 node 取近 lookback_days 的每日**累计**正确率,
比较「历史峰值」与「最新」,跌幅 ≥ min_drop 且最新有足够样本 → 判退步、按跌幅排序分严重度。

R8.1:数据源从旧 kp_mastery_snapshots(kp_key 快照)改为从 answer_log(node)**重放**
每日累计正确率(无需快照表)。可被学情报告、预警接口、通知推送共用。
"""
from __future__ import annotations

import uuid
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import AnswerLog

_LOOKBACK_DAYS = 21
_MIN_DROP = 0.15      # 正确率跌幅阈值
_MIN_TOTAL = 3        # 最新快照累计作答数下限（样本足够才预警）


def _severity(drop: float) -> str:
    if drop >= 0.30:
        return "high"
    if drop >= 0.20:
        return "mid"
    return "low"


async def detect_regressions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    lookback_days: int = _LOOKBACK_DAYS,
    min_drop: float = _MIN_DROP,
    min_total: int = _MIN_TOTAL,
) -> list[dict]:
    since = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    # 从 answer_log 逐事件重放每 node 的每日累计正确率(替代旧 kp_mastery_snapshots)。
    # 累计需从头算,故取该生全部作答;仅保留窗口内(>= since)的日末点。
    events = (await db.execute(
        select(AnswerLog.node_id, AnswerLog.is_correct, AnswerLog.answered_at)
        .where(AnswerLog.student_id == student_id, AnswerLog.node_id.isnot(None))
        .order_by(AnswerLog.answered_at.asc())
    )).all()

    _Snap = namedtuple("_Snap", "date accuracy total")
    cum: dict = defaultdict(lambda: [0, 0])          # node_id -> [correct, total] 累计
    by_node: dict = defaultdict(dict)                # node_id -> {date_iso: (correct, total)} 日末
    for node_id, is_correct, at in events:
        c = cum[node_id]
        c[1] += 1
        if is_correct:
            c[0] += 1
        d = at.date()
        if d >= since:
            by_node[node_id][d.isoformat()] = (c[0], c[1])

    if not by_node:
        return []
    names = {nid: nm for nid, nm in (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name)
        .where(KnowledgeNode.id.in_(list(by_node.keys()))))).all()}

    alerts: list[dict] = []
    for node_id, day_map in by_node.items():
        snaps = [_Snap(d, (c / t if t else 0.0), t) for d, (c, t) in sorted(day_map.items())]
        if len(snaps) < 2:
            continue
        latest = snaps[-1]
        if latest.total < min_total:
            continue
        peak = max(snaps[:-1], key=lambda s: s.accuracy)   # 最新之前的历史峰值
        drop = round(peak.accuracy - latest.accuracy, 4)
        if drop < min_drop:
            continue
        alerts.append({
            "kp_key": names.get(node_id, ""),
            "latest_accuracy": round(latest.accuracy, 4),
            "peak_accuracy": round(peak.accuracy, 4),
            "drop": drop,
            "severity": _severity(drop),
            "latest_date": latest.date,
            "peak_date": peak.date,
            "latest_total": latest.total,
        })

    alerts.sort(key=lambda a: a["drop"], reverse=True)
    return alerts


async def notify_student_regressions(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """检测退步并推送通知给学生本人 + 绑定家长 + 绑定老师（仅 high/mid 严重度）。

    返回 {alerts, notified_user_count}。调用方负责 commit。
    """
    from app.models.d1_users import StudentRelative, TeacherStudent, User
    from app.services import notification_service

    alerts = await detect_regressions(db, student_id=student_id)
    serious = [a for a in alerts if a["severity"] in ("high", "mid")]
    if not serious:
        return {"alerts": alerts, "notified_user_count": 0}

    nick = (await db.execute(
        select(User.nickname).where(User.id == student_id)
    )).scalar() or "孩子"
    kps = "、".join(a["kp_key"] for a in serious[:3])
    more = f" 等 {len(serious)} 项" if len(serious) > 3 else ""
    meta = {"student_id": str(student_id), "alerts": serious}

    # 接收人：学生本人 + 家长 + 老师
    targets: set[uuid.UUID] = {student_id}
    for rid in (await db.execute(
        select(StudentRelative.relative_id).where(
            StudentRelative.student_id == student_id,
            StudentRelative.is_active.is_(True),
        )
    )).scalars().all():
        targets.add(rid)
    for tid in (await db.execute(
        select(TeacherStudent.teacher_id).where(
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )).scalars().all():
        targets.add(tid)

    for uid in targets:
        is_self = uid == student_id
        title = "📉 知识点退步提醒"
        if is_self:
            content = f"你的「{kps}」{more}正确率下滑，建议尽快复习巩固。"
        else:
            content = f"{nick} 的「{kps}」{more}正确率下滑，建议关注督促复习。"
        # 复用学情类通知类型 report_ready（避免新增 enum 迁移）；meta.kind 标识退步
        await notification_service.emit(
            db, user_id=uid, type_="report_ready",
            title=title, content=content, meta={**meta, "kind": "kp_regression"},
        )
    return {"alerts": serious, "notified_user_count": len(targets)}


async def run_regression_alerts(db: AsyncSession) -> dict:
    """批量：对近期有作答的学生检测并推送退步预警（cron 调用）。调用方 commit。"""
    from datetime import date

    recent = date.today() - timedelta(days=_LOOKBACK_DAYS)
    student_ids = (await db.execute(
        select(AnswerLog.student_id)
        .where(AnswerLog.answered_at >= recent, AnswerLog.node_id.isnot(None))
        .distinct()
    )).scalars().all()
    total_notified = 0
    affected = 0
    for sid in student_ids:
        res = await notify_student_regressions(db, student_id=sid)
        if res["notified_user_count"] > 0:
            affected += 1
            total_notified += res["notified_user_count"]
    return {"students_with_regression": affected, "notifications_sent": total_notified}
