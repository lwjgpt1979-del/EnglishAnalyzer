"""机构批量续费 service（D-124）。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Student, User
from app.models.d2_payments import Membership, Order
from app.services import membership_service
from app.services.institution_purchase_service import _TIER_MONTHLY_FEN


async def list_renewable_students(
    db: AsyncSession, *, institution_id: uuid.UUID, expiring_days: int | None = None
) -> list[tuple[uuid.UUID, str | None, str, dt.datetime]]:
    q = (
        select(Student.id, User.nickname, Membership.tier, Membership.expires_at)
        .join(User, User.id == Student.id)
        .join(Membership, (Membership.user_id == Student.id) & (Membership.is_active.is_(True)))
        .where(Student.institution_id == institution_id)
    )
    if expiring_days is not None:
        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=expiring_days)
        q = q.where(Membership.expires_at <= cutoff)
    q = q.order_by(Membership.expires_at.asc())
    rows = (await db.execute(q)).all()
    return [(sid, nickname, str(tier), expires_at) for sid, nickname, tier, expires_at in rows]


async def batch_renew(
    db: AsyncSession, *, institution_id: uuid.UUID,
    student_ids: list[uuid.UUID], duration_months: int, operator_id: uuid.UUID,
) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    renewed_count = 0
    total_amount_fen = 0
    skipped: list[uuid.UUID] = []

    for sid in student_ids:
        student = await db.get(Student, sid)
        if student is None or student.institution_id != institution_id:
            skipped.append(sid)
            continue
        membership = await membership_service.get_active_membership(db, user_id=sid)
        if membership is None:
            skipped.append(sid)
            continue
        tier = str(membership.tier)
        amount = _TIER_MONTHLY_FEN.get(tier, 0) * duration_months
        order = Order(
            id=uuid.uuid4(),
            order_no=f"RNW{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
            payer_id=operator_id,
            beneficiary_id=sid,
            order_type="renew",  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            duration_months=duration_months,
            amount_fen=amount,
            status="paid",  # type: ignore[arg-type]
        )
        db.add(order)
        await db.flush()
        await membership_service.activate_membership(db, order=order)
        renewed_count += 1
        total_amount_fen += amount

    return {"renewed_count": renewed_count, "total_amount_fen": total_amount_fen, "skipped": skipped}
