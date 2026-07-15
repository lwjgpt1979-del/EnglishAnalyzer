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

from app.models.d16_question_domain import WrongRecord
from app.models.d5_learning import SpeakingSession, StudyCheckin
import sqlalchemy as sa

from app.models.d16_question_domain import AnswerLog
from app.services import checkin_service

# XP 权重
_XP_PRACTICE = 2
_XP_CHECKIN = 10
_XP_KP_MASTERED = 20
_XP_WRONG_MASTERED = 15
_XP_EXAM = 10
_XP_SPEAKING = 5
_XP_PER_LEVEL = 100
_MASTERY_THRESHOLD = 0.8  # KP 正确率达标线


async def get_summary(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    # ── 统计（各活动计数）────────────────────────────────────────────────
    # 练习题数只算 feature='practice'(考试作答另计场次 XP,避免同题既算练习又算考试双计)
    total_practice = int((await db.execute(
        select(func.count()).select_from(AnswerLog)
        .where(AnswerLog.student_id == student_id, AnswerLog.feature == "practice")
    )).scalar() or 0)

    checkin_days = int((await db.execute(
        select(func.count()).select_from(StudyCheckin)
        .where(StudyCheckin.student_id == student_id)
    )).scalar() or 0)

    # R8.1:掌握台账统一到 node,读 student_kp(correct=practice_count−wrong_count)
    from app.models.d16_question_domain import StudentKp
    mastered_kp = int((await db.execute(
        select(func.count()).select_from(StudentKp).where(
            StudentKp.student_id == student_id,
            StudentKp.practice_count > 0,
            (StudentKp.practice_count - StudentKp.wrong_count)
            >= _MASTERY_THRESHOLD * StudentKp.practice_count,
        )
    )).scalar() or 0)

    wrong_mastered = int((await db.execute(
        select(func.count()).select_from(WrongRecord).where(
            WrongRecord.student_id == student_id,
            WrongRecord.status == "mastered",
        )
    )).scalar() or 0)

    # 模拟考「场次」= 一次 submit_exam 的所有题共享同一 answered_at(Postgres now()=事务时间)。
    # 按 answered_at 分组即为场次;每场正确率 = 该组对数/总数,取最高。KP-First 无独立成绩表。
    exam_sessions = (await db.execute(
        select(func.count().label("total"),
               func.sum(sa.cast(AnswerLog.is_correct, sa.Integer)).label("correct"))
        .where(AnswerLog.student_id == student_id, AnswerLog.feature == "exam")
        .group_by(AnswerLog.answered_at))).all()
    exam_count = len(exam_sessions)
    best_exam_acc = max((int(r.correct or 0) / r.total for r in exam_sessions if r.total), default=0.0)

    speaking_count = int((await db.execute(
        select(func.count()).select_from(SpeakingSession)
        .where(SpeakingSession.student_id == student_id)
    )).scalar() or 0)
    best_speaking = int((await db.execute(
        select(func.coalesce(func.max(SpeakingSession.score), 0))
        .where(SpeakingSession.student_id == student_id)
    )).scalar() or 0)

    # ── 经验值 / 等级 ────────────────────────────────────────────────────
    xp = (total_practice * _XP_PRACTICE
          + checkin_days * _XP_CHECKIN
          + mastered_kp * _XP_KP_MASTERED
          + wrong_mastered * _XP_WRONG_MASTERED
          + exam_count * _XP_EXAM
          + speaking_count * _XP_SPEAKING)
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
        _ach("speak_starter", "开口第一句", "完成第一次口语练习", "🎤", speaking_count, 1),
        _ach("speak_20", "开口达人", "累计 20 次口语练习", "🗣️", speaking_count, 20),
        _ach("speak_ace", "口语高手", "单次口语评分达 90", "🌟",
             1 if best_speaking >= 90 else 0, 1),
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
            "speaking_count": speaking_count,
            "unlocked_achievements": sum(1 for a in achievements if a["unlocked"]),
            "total_achievements": len(achievements),
        },
    }
