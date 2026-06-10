"""学习激励中心 service（M10）。

无状态、无新表：经验值/等级/成就全部从现有活动数据实时派生。
- 经验值 XP：练习 2/题 · 打卡 10/天 · KP达标 20/个 · 攻克错题 15/道 · 模拟考 10/场
- 等级：每 100 XP 升 1 级
- 连续打卡 + 勋章：复用 checkin_service
- 成就：从统计派生解锁状态与进度
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import WrongQuestion
from app.models.d5_learning import StudyCheckin
from app.models.d4_knowledge import StudentKpMastery
from app.models.d12_v2_exams import SimExamSession, SimPracticeRecord
from app.services import checkin_service

# XP 权重
_XP_PRACTICE = 2
_XP_CHECKIN = 10
_XP_KP_MASTERED = 20
_XP_WRONG_MASTERED = 15
_XP_EXAM = 10
_XP_PER_LEVEL = 100
_MASTERY_THRESHOLD = 0.8  # KP 正确率达标线


async def get_summary(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    # ── 统计（各活动计数）────────────────────────────────────────────────
    total_practice = int((await db.execute(
        select(func.count()).select_from(SimPracticeRecord)
        .where(SimPracticeRecord.student_id == student_id)
    )).scalar() or 0)

    checkin_days = int((await db.execute(
        select(func.count()).select_from(StudyCheckin)
        .where(StudyCheckin.student_id == student_id)
    )).scalar() or 0)

    mastered_kp = int((await db.execute(
        select(func.count()).select_from(StudentKpMastery).where(
            StudentKpMastery.student_id == student_id,
            (StudentKpMastery.correct_count + StudentKpMastery.wrong_count) > 0,
            StudentKpMastery.correct_count
            >= _MASTERY_THRESHOLD * (StudentKpMastery.correct_count + StudentKpMastery.wrong_count),
        )
    )).scalar() or 0)

    wrong_mastered = int((await db.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == student_id,
            WrongQuestion.is_mastered.is_(True),
        )
    )).scalar() or 0)

    exam_count = int((await db.execute(
        select(func.count()).select_from(SimExamSession)
        .where(SimExamSession.student_id == student_id)
    )).scalar() or 0)
    best_exam_acc = float((await db.execute(
        select(func.coalesce(func.max(SimExamSession.accuracy), 0.0))
        .where(SimExamSession.student_id == student_id)
    )).scalar() or 0.0)

    # ── 经验值 / 等级 ────────────────────────────────────────────────────
    xp = (total_practice * _XP_PRACTICE
          + checkin_days * _XP_CHECKIN
          + mastered_kp * _XP_KP_MASTERED
          + wrong_mastered * _XP_WRONG_MASTERED
          + exam_count * _XP_EXAM)
    level = xp // _XP_PER_LEVEL + 1
    xp_in_level = xp % _XP_PER_LEVEL
    xp_to_next = _XP_PER_LEVEL - xp_in_level

    # ── 连续打卡 + 勋章（复用 checkin_service）──────────────────────────
    st = await checkin_service.get_checkin_status(db, student_id=student_id)
    badges = checkin_service._badges(st["longest_streak"])

    # ── 成就（派生解锁 + 进度）──────────────────────────────────────────
    def _ach(key, name, desc, icon, current, target):
        return {
            "key": key, "name": name, "desc": desc, "icon": icon,
            "current": int(current), "target": int(target),
            "unlocked": current >= target,
            "progress": round(min(current / target, 1.0), 3) if target else 1.0,
        }

    achievements = [
        _ach("first_step", "初次出发", "完成第一次练习", "🌱", total_practice, 1),
        _ach("practice_100", "练习达人", "累计练习 100 题", "💪", total_practice, 100),
        _ach("streak_7", "坚持一周", "连续打卡 7 天", "🔥", st["longest_streak"], 7),
        _ach("streak_30", "毅力满满", "连续打卡 30 天", "⚡", st["longest_streak"], 30),
        _ach("kp_master", "知识点大师", "10 个知识点达到掌握", "🧠", mastered_kp, 10),
        _ach("wrong_slayer", "错题克星", "攻克 10 道错题", "🎯", wrong_mastered, 10),
        _ach("exam_ace", "考场之星", "模拟考正确率达 80%", "🏆",
             1 if best_exam_acc >= 0.8 else 0, 1),
    ]

    return {
        "level": level,
        "xp": xp,
        "xp_in_level": xp_in_level,
        "xp_to_next": xp_to_next,
        "current_streak": st["current_streak"],
        "longest_streak": st["longest_streak"],
        "checked_in_today": st["checked_in_today"],
        "badges": badges,
        "achievements": achievements,
        "stats": {
            "total_practice": total_practice,
            "checkin_days": checkin_days,
            "mastered_kp": mastered_kp,
            "wrong_mastered": wrong_mastered,
            "exam_count": exam_count,
            "unlocked_achievements": sum(1 for a in achievements if a["unlocked"]),
            "total_achievements": len(achievements),
        },
    }
