"""运营数据大盘统计（M5 / D-099）。只读聚合。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User, Teacher
from app.models.d2_payments import Order
from app.models.d12_v2_exams import SimulatedQuestion
from app.models.d25_kp_lecture import KpLecture
from app.schemas.admin import AdminOverviewOut

_STATUSES = ["draft", "reviewing", "published", "retired"]


def _normalize(rows: list[tuple[str, int]]) -> dict[str, int]:
    out = {s: 0 for s in _STATUSES}
    for status, cnt in rows:
        out[str(status)] = cnt
    return out


async def get_overview(db: AsyncSession) -> AdminOverviewOut:
    q_rows = (await db.execute(
        select(SimulatedQuestion.status, func.count()).group_by(SimulatedQuestion.status)
    )).all()
    # 考点讲解:kp_lecture(按类型的教学环节),按状态计数(draft/published)
    c_rows = (await db.execute(
        select(KpLecture.status, func.count()).group_by(KpLecture.status)
    )).all()
    total_users = (await db.execute(
        select(func.count()).select_from(User)
    )).scalar_one()
    paid_orders = (await db.execute(
        select(func.count()).select_from(Order).where(Order.status == "paid")
    )).scalar_one()
    pending_teachers = (await db.execute(
        select(func.count()).select_from(Teacher).where(Teacher.cert_status == "pending")
    )).scalar_one()
    return AdminOverviewOut(
        questions_by_status=_normalize(q_rows),
        contents_by_status=_normalize(c_rows),
        total_users=total_users,
        paid_orders=paid_orders,
        pending_teachers=pending_teachers,
    )
