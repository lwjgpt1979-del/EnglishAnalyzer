"""机构批量续费 service（V2 M26 — 基于 purchased_semesters）。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Student, User
from app.models.d14_v2_semesters import PurchasedSemester

# 按学期计价（分）
_TIER_SEMESTER_FEN: dict[str, int] = {
    "basic": 3900,
    "pro": 7900,
    "promax": 15900,
}

# V1 fallback（仅供 duration_months 字段兼容）
_TIER_MONTHLY_FEN: dict[str, int] = {"basic": 650, "pro": 1317, "promax": 2650}

DAYS_PER_SEMESTER = 183


async def list_renewable_students(
    db: AsyncSession, *, institution_id: uuid.UUID, expiring_days: int | None = None
) -> list[tuple[uuid.UUID, str | None, str, dt.datetime]]:
    """返回机构内学生的最新学期到期信息（V2: purchased_semesters）。"""
    q = (
        select(Student.id, User.nickname, PurchasedSemester.tier, PurchasedSemester.expires_at)
        .join(User, User.id == Student.id)
        .join(PurchasedSemester, PurchasedSemester.user_id == Student.id)
        .where(Student.institution_id == institution_id)
        .order_by(Student.id, PurchasedSemester.expires_at.desc())
        .distinct(Student.id)
    )
    if expiring_days is not None:
        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=expiring_days)
        q = q.where(PurchasedSemester.expires_at <= cutoff)
    rows = (await db.execute(q)).all()
    return [(sid, nickname, str(tier), expires_at) for sid, nickname, tier, expires_at in rows]


async def batch_renew(
    db: AsyncSession, *,
    institution_id: uuid.UUID,
    student_ids: list[uuid.UUID],
    semesters: int = 1,
    duration_months: int | None = None,  # V1 兼容，已废弃
    operator_id: uuid.UUID,
) -> dict:
    """批量续费：将学生的 purchased_semesters.expires_at 延长 semesters * 183 天。"""
    # V1 兼容：如果只传了 duration_months 则折算为 semesters
    if semesters == 1 and duration_months is not None:
        semesters = max(1, round(duration_months / 6))

    now = dt.datetime.now(dt.timezone.utc)
    renewed_count = 0
    total_amount_fen = 0
    skipped: list[uuid.UUID] = []

    for sid in student_ids:
        student = await db.get(Student, sid)
        if student is None or student.institution_id != institution_id:
            skipped.append(sid)
            continue

        # 找该学生的最新 purchased_semester（按 expires_at 倒序）
        result = await db.execute(
            select(PurchasedSemester)
            .where(PurchasedSemester.user_id == sid)
            .order_by(PurchasedSemester.expires_at.desc())
            .limit(1)
        )
        ps = result.scalar_one_or_none()
        if ps is None:
            skipped.append(sid)
            continue

        tier = str(ps.tier)
        amount = _TIER_SEMESTER_FEN.get(tier, 3900) * semesters

        # 延长：从 max(expires_at, now) 起顺延
        base = max(ps.expires_at, now)
        ps.expires_at = base + dt.timedelta(days=semesters * DAYS_PER_SEMESTER)

        renewed_count += 1
        total_amount_fen += amount

    await db.flush()
    return {"renewed_count": renewed_count, "total_amount_fen": total_amount_fen, "skipped": skipped}
