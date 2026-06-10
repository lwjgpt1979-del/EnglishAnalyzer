"""学情退步预警 service（M13）。

从 kp_mastery_snapshots 检测「知识点正确率下滑」：
对每个 KP 取近 lookback_days 的日快照，比较「历史峰值」与「最新」正确率，
跌幅 ≥ min_drop 且最新有足够样本 → 判为退步，按跌幅排序、分严重度。

无新表；可被学情报告、预警接口、通知推送共用。
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import KpMasterySnapshot

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
    rows = (await db.execute(
        select(KpMasterySnapshot)
        .where(
            KpMasterySnapshot.student_id == student_id,
            KpMasterySnapshot.snapshot_date >= since,
        )
        .order_by(KpMasterySnapshot.kp_key, KpMasterySnapshot.snapshot_date)
    )).scalars().all()

    by_kp: dict[str, list[KpMasterySnapshot]] = defaultdict(list)
    for r in rows:
        by_kp[r.kp_key].append(r)

    alerts: list[dict] = []
    for kp_key, snaps in by_kp.items():
        if len(snaps) < 2:
            continue
        latest = snaps[-1]
        latest_total = latest.correct_count + latest.wrong_count
        if latest_total < min_total:
            continue
        # 历史峰值（最新之前的最高正确率）
        earlier = snaps[:-1]
        peak = max(earlier, key=lambda s: s.accuracy)
        drop = round(float(peak.accuracy) - float(latest.accuracy), 4)
        if drop < min_drop:
            continue
        alerts.append({
            "kp_key": kp_key,
            "latest_accuracy": round(float(latest.accuracy), 4),
            "peak_accuracy": round(float(peak.accuracy), 4),
            "drop": drop,
            "severity": _severity(drop),
            "latest_date": latest.snapshot_date.isoformat(),
            "peak_date": peak.snapshot_date.isoformat(),
            "latest_total": latest_total,
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
    """批量：对近期有快照的学生检测并推送退步预警（cron 调用）。调用方 commit。"""
    from datetime import date

    recent = date.today() - timedelta(days=_LOOKBACK_DAYS)
    student_ids = (await db.execute(
        select(KpMasterySnapshot.student_id)
        .where(KpMasterySnapshot.snapshot_date >= recent)
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
