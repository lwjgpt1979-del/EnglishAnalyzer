"""数据大盘（§5.5）：用户/角色/地区/会员/营收/功能使用/机构 关键指标。

全部从现有表实时聚合，无新表。金额单位转元。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User, Institution
from app.models.d2_payments import Membership, Order, RefundRecord
from app.models.d5_learning import Essay, StudyCheckin, ListeningWrongQuestion  # noqa: F401
from app.models.d5_learning import VocabPronLog
from app.models.d12_v2_exams import SimPracticeRecord
from app.models.d3_wrong_questions import WrongQuestion


def _yuan(fen) -> float:
    return round((fen or 0) / 100, 2)


async def get_dashboard(db: AsyncSession) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    today = dt.datetime(now.year, now.month, now.day, tzinfo=dt.timezone.utc)
    month0 = dt.datetime(now.year, now.month, 1, tzinfo=dt.timezone.utc)
    d7 = today - dt.timedelta(days=7)
    d30 = today - dt.timedelta(days=30)

    async def _count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    # —— 用户与增长 ——
    total_users = await _count(select(func.count()).select_from(User))
    role_rows = (await db.execute(
        select(User.role, func.count()).group_by(User.role))).all()
    roles = {str(r): c for r, c in role_rows}

    def _new(since):
        return select(func.count()).select_from(User).where(User.created_at >= since)
    new_today = await _count(_new(today))
    new_7d = await _count(_new(d7))
    new_30d = await _count(_new(d30))

    region_rows = (await db.execute(
        select(User.city_code, func.count()).where(User.city_code.isnot(None))
        .group_by(User.city_code).order_by(func.count().desc()).limit(10))).all()
    regions = [{"city_code": c, "count": n} for c, n in region_rows]

    # —— 会员与营收 ——
    mem_rows = (await db.execute(
        select(Membership.tier, func.count()).where(Membership.is_active.is_(True))
        .group_by(Membership.tier))).all()
    members = {str(t): c for t, c in mem_rows}
    paid_member_count = sum(c for t, c in mem_rows if str(t) != "free")
    students = roles.get("student", 0)
    pay_conversion = round(paid_member_count / students * 100, 1) if students else 0.0

    paid_status = ("paid", "refunded", "partial_refunded")

    async def _gmv(since):
        return _yuan(await db.scalar(
            select(func.coalesce(func.sum(Order.amount_fen), 0)).where(and_(
                Order.status.in_(paid_status), Order.paid_at >= since))) or 0)
    gmv_today = await _gmv(today)
    gmv_month = await _gmv(month0)
    refund_month_fen = int(await db.scalar(
        select(func.coalesce(func.sum(RefundRecord.amount_fen), 0)).where(and_(
            RefundRecord.status == "completed", RefundRecord.reviewed_at >= month0))) or 0)
    gmv_month_fen = int(await db.scalar(
        select(func.coalesce(func.sum(Order.amount_fen), 0)).where(and_(
            Order.status.in_(paid_status), Order.paid_at >= month0))) or 0)
    refund_rate = round(refund_month_fen / gmv_month_fen * 100, 1) if gmv_month_fen else 0.0

    # —— 今日核心功能使用 ——
    async def _today(model, ts_col):
        return await _count(select(func.count()).select_from(model).where(ts_col >= today))
    usage_today = {
        "checkins": await _count(
            select(func.count()).select_from(StudyCheckin).where(StudyCheckin.checkin_date == now.date())),
        "practice": await _today(SimPracticeRecord, SimPracticeRecord.created_at),
        "wrong_upload": await _today(WrongQuestion, WrongQuestion.created_at),
        "essays": await _today(Essay, Essay.created_at),
        "shadow": await _today(VocabPronLog, VocabPronLog.created_at),
    }

    # —— 活跃（DAU/MAU/趋势）——
    from app.services import activity_service
    active = await activity_service.active_metrics(db)

    # —— 机构 ——
    inst_active = await _count(
        select(func.count()).select_from(Institution).where(Institution.status == "active"))

    return {
        "users": {
            "total": total_users, "roles": roles,
            "new_today": new_today, "new_7d": new_7d, "new_30d": new_30d,
            "regions_top": regions,
        },
        "membership": {
            "active_by_tier": members, "paid_members": paid_member_count,
            "pay_conversion_pct": pay_conversion,
        },
        "revenue": {
            "gmv_today_yuan": gmv_today, "gmv_month_yuan": gmv_month,
            "refund_month_yuan": _yuan(refund_month_fen), "refund_rate_pct": refund_rate,
        },
        "usage_today": usage_today,
        "active": active,
        "institution": {"active": inst_active},
        "generated_at": now.isoformat(),
    }
