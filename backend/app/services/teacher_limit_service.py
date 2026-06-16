"""老师月度限额（§5.6）：后台统一配置 + 个体覆盖 + 用量计数 + 预警。

全局默认存 system_configs.teacher_limits；个体覆盖在 teachers 列
（max_students / monthly_paper_quota / monthly_grading_quota，NULL=随全局）。
三类用量均按自然月从现有表实时计数，无计数表：
  - students：当前 active TeacherStudent 数（非月度，是并发上限）
  - paper：本月 Assignment 数
  - grading：本月 TeacherComment 数（老师批改/点评）
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Teacher, TeacherStudent
from app.models.d3_wrong_questions import TeacherComment
from app.models.d9_system import SystemConfig

_KEY = "teacher_limits"
DEFAULTS = {
    "max_students": 50,
    "monthly_paper_quota": 10,
    "monthly_grading_quota": 20,
    "warn_threshold_pct": 20,
    "reset_day": 1,
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def get_limits(db: AsyncSession) -> dict:
    """全局默认配置（缺省回 DEFAULTS）。"""
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    out = dict(DEFAULTS)
    if cfg is not None and isinstance(cfg.value, dict):
        for k in DEFAULTS:
            if cfg.value.get(k) is not None:
                out[k] = int(cfg.value[k])
    return out


async def update_limits(db: AsyncSession, *, fields: dict, admin_id: uuid.UUID) -> dict:
    cur = await get_limits(db)
    for k in DEFAULTS:
        if k in fields and fields[k] is not None:
            v = int(fields[k])
            if v < 0:
                raise AppError(code=400, message=f"{k} 不能为负")
            if k == "warn_threshold_pct" and v > 100:
                raise AppError(code=400, message="预警阈值需在 0-100")
            if k == "reset_day" and not (1 <= v <= 28):
                raise AppError(code=400, message="月度重置日需在 1-28")
            cur[k] = v
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=cur,
                            description="老师月度限额全局默认（§5.6）", updated_by=admin_id))
    else:
        cfg.value = cur
        cfg.updated_by = admin_id
    await db.flush()
    return cur


async def effective_for(db: AsyncSession, teacher: Teacher) -> dict:
    """该老师的有效额度：个体覆盖优先，否则全局默认。"""
    g = await get_limits(db)
    return {
        "max_students": teacher.max_students if teacher.max_students is not None else g["max_students"],
        "monthly_paper_quota": teacher.monthly_paper_quota if teacher.monthly_paper_quota is not None else g["monthly_paper_quota"],
        "monthly_grading_quota": teacher.monthly_grading_quota if teacher.monthly_grading_quota is not None else g["monthly_grading_quota"],
        "warn_threshold_pct": g["warn_threshold_pct"],
        "reset_day": g["reset_day"],
    }


def _month_start(reset_day: int, now: dt.datetime | None = None) -> dt.datetime:
    """按 reset_day 计算当前计费月起点。"""
    now = now or _now()
    rd = max(1, min(28, reset_day or 1))
    start = now.replace(day=rd, hour=0, minute=0, second=0, microsecond=0)
    if now.day < rd:
        # 还没到本月重置日 → 起点为上月重置日
        prev = (start.replace(day=1) - dt.timedelta(days=1)).replace(
            day=rd, hour=0, minute=0, second=0, microsecond=0)
        return prev
    return start


async def _students_used(db: AsyncSession, teacher_id: uuid.UUID) -> int:
    return int(await db.scalar(
        select(func.count()).select_from(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.status == "active")) or 0)


async def _paper_used(db: AsyncSession, teacher_id: uuid.UUID, since: dt.datetime) -> int:
    from app.models.d7_teacher import Assignment
    return int(await db.scalar(
        select(func.count()).select_from(Assignment).where(
            Assignment.teacher_id == teacher_id, Assignment.created_at >= since)) or 0)


async def _grading_used(db: AsyncSession, teacher_id: uuid.UUID, since: dt.datetime) -> int:
    return int(await db.scalar(
        select(func.count()).select_from(TeacherComment).where(
            TeacherComment.teacher_id == teacher_id, TeacherComment.created_at >= since)) or 0)


async def quota_overview(db: AsyncSession, *, teacher_id: uuid.UUID) -> dict:
    """老师自查：三类额度 used/limit/剩余%。"""
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None:
        raise AppError(code=404, message="老师不存在")
    eff = await effective_for(db, teacher)
    ms = _month_start(eff["reset_day"])
    students = await _students_used(db, teacher_id)
    paper = await _paper_used(db, teacher_id, ms)
    grading = await _grading_used(db, teacher_id, ms)

    def _blk(used, limit):
        remain = max(0, limit - used)
        return {"used": used, "limit": limit, "remaining": remain,
                "remaining_pct": round(remain / limit * 100, 1) if limit else 100.0}
    return {
        "warn_threshold_pct": eff["warn_threshold_pct"], "reset_day": eff["reset_day"],
        "students": _blk(students, eff["max_students"]),
        "paper": _blk(paper, eff["monthly_paper_quota"]),
        "grading": _blk(grading, eff["monthly_grading_quota"]),
    }


# ── 闸门 + 预警 ──────────────────────────────────────────────────────────────
async def assert_can_bind_student(db: AsyncSession, *, teacher_id: uuid.UUID) -> None:
    """绑定学生前校验并发上限（§5.6）。仅拦新增，不回溯。"""
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None:
        return
    eff = await effective_for(db, teacher)
    used = await _students_used(db, teacher_id)
    if used >= eff["max_students"]:
        raise AppError(code=403, message=f"绑定学生数已达上限（{eff['max_students']}名）")


async def assert_can_create_paper(db: AsyncSession, *, teacher_id: uuid.UUID) -> None:
    """出卷前校验月度上限（§5.6）。"""
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None:
        return
    eff = await effective_for(db, teacher)
    ms = _month_start(eff["reset_day"])
    used = await _paper_used(db, teacher_id, ms)
    if used >= eff["monthly_paper_quota"]:
        raise AppError(code=403, message="本月出卷额度已用尽")


async def check_grading_and_warn(db: AsyncSession, *, teacher_id: uuid.UUID) -> None:
    """批改/点评前校验月度上限 + 预警（§5.6）。在新增 TeacherComment 之前调用。"""
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None:
        return
    eff = await effective_for(db, teacher)
    ms = _month_start(eff["reset_day"])
    limit = eff["monthly_grading_quota"]
    used = await _grading_used(db, teacher_id, ms)   # 本次之前的用量
    if used >= limit:
        raise AppError(code=403, message="本月批改/点评额度已用尽")
    # 预警：本次（used+1）越过阈值线则发一次站内通知
    await _maybe_warn(db, teacher_id=teacher_id, kind="grading", label="批改/点评",
                      used_after=used + 1, limit=limit, thr=eff["warn_threshold_pct"])


async def _maybe_warn(db: AsyncSession, *, teacher_id: uuid.UUID, kind: str, label: str,
                      used_after: int, limit: int, thr: int) -> None:
    if limit <= 0 or thr <= 0:
        return
    warn_line = limit * (100 - thr) / 100.0   # 用量超过此值即剩余<阈值
    if (used_after - 1) < warn_line <= used_after:   # 恰好本次越线 → 只提醒一次
        remain = max(0, limit - used_after)
        from app.services import notification_service
        try:
            await notification_service.emit(
                db, user_id=teacher_id, type_="system", title="额度预警",
                content=f"您本月「{label}」额度仅剩 {remain}/{limit}，请合理安排。",
                meta={"kind": kind})
        except Exception:
            pass


# ── 管理：个体覆盖 ──────────────────────────────────────────────────────────
async def set_teacher_override(db: AsyncSession, *, teacher_id: uuid.UUID, fields: dict) -> Teacher:
    """设单个老师的额度覆盖（值传 null/省略=随全局）。"""
    t = await db.get(Teacher, teacher_id)
    if t is None:
        raise AppError(code=404, message="老师不存在")
    if "max_students" in fields:
        v = fields["max_students"]
        t.max_students = int(v) if v not in (None, "") else 50   # max_students 非空，清空回默认 50
    if "monthly_paper_quota" in fields:
        v = fields["monthly_paper_quota"]
        t.monthly_paper_quota = int(v) if v not in (None, "") else None
    if "monthly_grading_quota" in fields:
        v = fields["monthly_grading_quota"]
        t.monthly_grading_quota = int(v) if v not in (None, "") else None
    await db.flush()
    return t
