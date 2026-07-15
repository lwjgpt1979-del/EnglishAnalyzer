"""学情周报服务（V2 M30）。
每周一 08:00 由 cron 调用 run_weekly_reports()，给每个绑定家长发送上周学情摘要。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import StudentRelative, User
from app.models.d16_question_domain import AnswerLog
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.models.d5_learning import StudyCheckin
from app.services import notification_service


# ── 数据类 ─────────────────────────────────────────────────────────────────────

@dataclass
class WeeklyReportData:
    student_id: uuid.UUID
    student_nickname: str
    week_start: date
    week_end: date
    checkin_days: int = 0
    practice_count: int = 0
    wrong_paper_count: int = 0
    max_streak: int = 0
    weak_kp_names: list[str] = field(default_factory=list)


# ── 内部工具 ────────────────────────────────────────────────────────────────────

def _last_week_range() -> tuple[date, date]:
    """返回（上周一，上周日）。"""
    today = datetime.now(timezone.utc).date()
    # weekday(): 0=Monday … 6=Sunday
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def _week_start_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _week_end_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


# ── 周报生成 ────────────────────────────────────────────────────────────────────

async def generate_student_weekly_report(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    week_start: date,
    week_end: date,
) -> WeeklyReportData:
    """生成单个学生的上周学情数据。"""

    # 取学生昵称
    user_row = await db.get(User, student_id)
    nickname = (user_row.nickname or "同学") if user_row else "同学"

    ws_dt = _week_start_dt(week_start)
    we_dt = _week_end_dt(week_end)

    # 本周打卡天数
    checkin_q = await db.execute(
        select(func.count()).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date >= week_start,
            StudyCheckin.checkin_date <= week_end,
        )
    )
    checkin_days = checkin_q.scalar() or 0

    # 本周最高连续打卡天数
    streak_q = await db.execute(
        select(func.max(StudyCheckin.streak_days)).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date >= week_start,
            StudyCheckin.checkin_date <= week_end,
        )
    )
    max_streak = streak_q.scalar() or 0

    # 本周做题数(KP-First:answer_log 练习/模拟考/自适应作答真值)
    practice_q = await db.execute(
        select(func.count()).select_from(AnswerLog).where(
            AnswerLog.student_id == student_id,
            AnswerLog.answered_at >= ws_dt,
            AnswerLog.answered_at <= we_dt,
        )
    )
    practice_count = practice_q.scalar() or 0

    # 本周整卷错题数（JOIN user_uploaded_papers 过滤 student_id）
    paper_q = await db.execute(
        select(func.count()).select_from(UserPaperQuestion).join(
            UserUploadedPaper,
            UserPaperQuestion.user_paper_id == UserUploadedPaper.id,
        ).where(
            UserUploadedPaper.student_id == student_id,
            UserPaperQuestion.is_wrong == True,
            UserPaperQuestion.created_at >= ws_dt,
            UserPaperQuestion.created_at <= we_dt,
        )
    )
    wrong_paper_count = paper_q.scalar() or 0

    # 近 30 天薄弱知识点（top-2）—— 统一错题中枢 wrong_record 的错题归类名
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    from app.models.d16_question_domain import WrongRecord
    kp_rows = await db.execute(
        select(WrongRecord.kp_name).where(
            WrongRecord.student_id == student_id,
            WrongRecord.kp_name.isnot(None),
            WrongRecord.created_at >= thirty_days_ago,
        )
    )
    kp_counter: dict[str, int] = {}
    for (kp,) in kp_rows:
        if kp:
            kp_counter[kp] = kp_counter.get(kp, 0) + 1
    weak_kp_names = [k for k, _ in sorted(kp_counter.items(), key=lambda x: -x[1])][:2]

    return WeeklyReportData(
        student_id=student_id,
        student_nickname=nickname,
        week_start=week_start,
        week_end=week_end,
        checkin_days=checkin_days,
        practice_count=practice_count,
        wrong_paper_count=wrong_paper_count,
        max_streak=max_streak,
        weak_kp_names=weak_kp_names,
    )


def _build_notification_body(r: WeeklyReportData) -> str:
    total_questions = r.practice_count + r.wrong_paper_count
    weak_str = ""
    if r.weak_kp_names:
        weak_str = f"，薄弱点：{'、'.join(r.weak_kp_names)}"
    return (
        f"打卡 {r.checkin_days}/7 天，"
        f"做题 {total_questions} 道"
        f"{weak_str}"
    )


# ── cron 入口 ───────────────────────────────────────────────────────────────────

async def run_weekly_reports(db: AsyncSession) -> dict:
    """遍历所有绑定了家长的学生，生成上周周报并给家长发站内通知。
    供 cron 每周一 08:00 调用（之后 commit 由调用方负责）。
    """
    week_start, week_end = _last_week_range()

    # 取所有活跃绑定（student_id, relative_id）
    bindings_q = await db.execute(
        select(StudentRelative.student_id, StudentRelative.relative_id).where(
            StudentRelative.is_active == True,
            StudentRelative.unbound_at == None,  # noqa: E711
        )
    )
    bindings: list[tuple[uuid.UUID, uuid.UUID]] = list(bindings_q.fetchall())

    if not bindings:
        return {"students_processed": 0, "relatives_notified": 0}

    # 按学生去重，批量生成周报
    student_ids = list({sid for sid, _ in bindings})
    reports: dict[uuid.UUID, WeeklyReportData] = {}
    for sid in student_ids:
        reports[sid] = await generate_student_weekly_report(
            db, student_id=sid, week_start=week_start, week_end=week_end
        )

    # 给每个家长发站内通知
    notified = 0
    for student_id, relative_id in bindings:
        report = reports[student_id]
        title = f"📊 {report.student_nickname}本周学情周报"
        body = _build_notification_body(report)
        await notification_service.emit(
            db,
            user_id=relative_id,
            type_="weekly_report",
            title=title,
            content=body,
            meta={
                "student_id": str(student_id),
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "checkin_days": report.checkin_days,
                "practice_count": report.practice_count,
                "wrong_paper_count": report.wrong_paper_count,
                "max_streak": report.max_streak,
                "weak_kp_names": report.weak_kp_names,
            },
        )
        notified += 1

    return {"students_processed": len(student_ids), "relatives_notified": notified}
