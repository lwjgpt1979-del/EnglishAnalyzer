"""V2 学期会员服务（D-079 / M1）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d14_v2_semesters import PurchasedSemester

SEMESTER_DURATION_DAYS = 180  # 6 个月
TIER_RANK = {"basic": 1, "pro": 2, "promax": 3}


async def list_my_semesters(
    db: AsyncSession, *, user_id: uuid.UUID,
) -> list[PurchasedSemester]:
    r = await db.execute(
        select(PurchasedSemester)
        .where(PurchasedSemester.user_id == user_id)
        .order_by(PurchasedSemester.expires_at.desc())
    )
    return list(r.scalars().all())


async def query_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
) -> tuple[bool, str | None, datetime | None]:
    """返回 (可访问, 最高已购 tier, expires_at)。"""
    now = datetime.now(timezone.utc)
    r = await db.execute(
        select(PurchasedSemester).where(
            PurchasedSemester.user_id == user_id,
            PurchasedSemester.textbook_version == textbook_version,
            PurchasedSemester.grade == grade,
            PurchasedSemester.semester == semester,
            PurchasedSemester.expires_at > now,
        )
    )
    items = list(r.scalars().all())
    if not items:
        return False, None, None
    best = max(items, key=lambda p: (TIER_RANK[str(p.tier)], p.expires_at))
    return True, str(best.tier), best.expires_at


async def assert_can_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
    required_tier: str = "basic",
) -> None:
    ok, tier, _ = await query_access(
        db, user_id=user_id, textbook_version=textbook_version,
        grade=grade, semester=semester,
    )
    if not ok:
        raise AppError(code=403, message="未购买该学期会员")
    if TIER_RANK[tier] < TIER_RANK[required_tier]:
        raise AppError(code=403, message=f"需要 {required_tier} 及以上档位")


async def create_purchased_semesters(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tier: str,
    semesters: list[dict],
    order_id: uuid.UUID,
) -> list[PurchasedSemester]:
    """订单支付成功后为每个学期创建一行 PurchasedSemester。"""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SEMESTER_DURATION_DAYS)

    existing = await db.execute(
        select(PurchasedSemester).where(PurchasedSemester.user_id == user_id)
    )
    base_no = len(list(existing.scalars().all()))

    created: list[PurchasedSemester] = []
    for i, s in enumerate(semesters, start=1):
        ps = PurchasedSemester(
            id=uuid.uuid4(),
            user_id=user_id,
            textbook_version=s["textbook_version"],
            grade=s["grade"],
            semester=s["semester"],  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            semester_no=base_no + i,
            started_at=now,
            expires_at=expires,
            order_id=order_id,
        )
        db.add(ps)
        created.append(ps)
    await db.flush()
    return created
