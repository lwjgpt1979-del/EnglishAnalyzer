"""机构会员到期预警（D-127）：名下学生近 N 天到期 → 站内通知机构管理员。"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import Student, User
from app.models.d2_payments import Membership
from app.services import notification_service


async def run_expiry_alerts(db: AsyncSession, *, days: int = 30) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now + dt.timedelta(days=days)

    admin_rows = (await db.execute(
        select(User.id, User.institution_id).where(
            User.role == "institution_admin",
            User.institution_id.is_not(None),
        )
    )).all()
    by_inst: dict = {}
    for uid, inst_id in admin_rows:
        by_inst.setdefault(inst_id, []).append(uid)

    institutions_notified = 0
    admins_notified = 0
    for inst_id, admins in by_inst.items():
        student_ids = select(Student.id).where(Student.institution_id == inst_id)
        expiring = (await db.execute(
            select(func.count(func.distinct(Membership.user_id))).where(
                Membership.user_id.in_(student_ids),
                Membership.is_active.is_(True),
                Membership.expires_at.is_not(None),
                Membership.expires_at >= now,
                Membership.expires_at <= cutoff,
            )
        )).scalar_one()
        if expiring <= 0:
            continue
        institutions_notified += 1
        for admin_id in admins:
            await notification_service.emit(
                db, user_id=admin_id, type_="membership",
                title="会员到期预警",
                content=f"您机构有 {expiring} 名学生会员将在 {days} 天内到期，请及时续费。",
            )
            admins_notified += 1

    return {"institutions_notified": institutions_notified, "admins_notified": admins_notified}
