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
from app.models.d16_question_domain import AnswerLog
from app.models.d16_question_domain import WrongRecord


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
        "practice": await _today(AnswerLog, AnswerLog.answered_at),
        "wrong_upload": await _today(WrongRecord, WrongRecord.created_at),
        "essays": await _today(Essay, Essay.created_at),
        "shadow": await _today(VocabPronLog, VocabPronLog.created_at),
    }

    # —— 活跃（DAU/MAU/趋势）——
    from app.services import activity_service
    active = await activity_service.active_metrics(db)

    # —— 内容质量反馈（§5.5）——
    from app.services import content_feedback_service
    feedback = await content_feedback_service.stats(db, since=month0)

    # —— ARPU（§5.5）：本月 GMV / 本月付费人数 ——
    payers_month = await _count(
        select(func.count(func.distinct(Order.beneficiary_id))).where(and_(
            Order.status.in_(paid_status), Order.paid_at >= month0)))
    arpu_month = round(gmv_month_fen / 100 / payers_month, 2) if payers_month else 0.0

    # —— 错题复盘率（§5.5，拆 验证通过 / 手动标记）——
    wq_total = await _count(select(func.count()).select_from(WrongRecord))
    wq_mastered = await _count(
        select(func.count()).select_from(WrongRecord).where(WrongRecord.status == "mastered"))
    src_rows = (await db.execute(
        select(WrongRecord.mastery_source, func.count())
        .where(WrongRecord.status == "mastered")
        .group_by(WrongRecord.mastery_source))).all()
    src = {str(s): int(c) for s, c in src_rows}
    review_rate = {
        "total": wq_total, "mastered": wq_mastered,
        "rate_pct": round(wq_mastered / wq_total * 100, 1) if wq_total else 0.0,
        "by_review": src.get("review", 0), "by_manual": src.get("manual", 0),
        "by_unknown": src.get("None", 0),
    }

    # —— OCR 识别成功率（§5.5）：completed / 有状态总数（错题单题 + 整卷）——
    from app.models.d13_v2_user_papers import UserUploadedPaper
    async def _ocr_rate(model, col):
        tot = await _count(select(func.count()).select_from(model).where(col.isnot(None)))
        ok = await _count(select(func.count()).select_from(model).where(col == "completed"))
        return {"total": tot, "completed": ok,
                "rate_pct": round(ok / tot * 100, 1) if tot else 0.0}
    # 拍照单题已下线,OCR 指标仅保留整卷上传(uploaded_papers)
    ocr_success = {
        "uploaded_papers": await _ocr_rate(UserUploadedPaper, UserUploadedPaper.ocr_status),
    }

    # —— OCR 手动修正率(§5.5):拍照单题下线后无逐条修正标记,置零占位 ——
    ocr_completed_n = await _count(
        select(func.count()).select_from(UserUploadedPaper).where(UserUploadedPaper.ocr_status == "completed"))
    ocr_correction = {
        "completed": ocr_completed_n, "corrected": 0, "rate_pct": 0.0,
    }

    # —— 题库练习来源拆分（§5.5）：独立入口 vs 复盘触发 ——
    from app.models.d6_ai_questions import PracticeRecord
    pr_rows = (await db.execute(
        select(PracticeRecord.trigger_type, func.count())
        .group_by(PracticeRecord.trigger_type))).all()
    pr = {str(t): int(c) for t, c in pr_rows}
    pr_free = pr.get("module8_free", 0)
    pr_review = pr.get("wrong_q_followup", 0)
    pr_total = pr_free + pr_review
    practice_split = {
        "free_entry": pr_free, "review_triggered": pr_review, "total": pr_total,
        "free_pct": round(pr_free / pr_total * 100, 1) if pr_total else 0.0,
        "review_pct": round(pr_review / pr_total * 100, 1) if pr_total else 0.0,
    }

    # —— 机构账号续费率（§5.5，近似：复购机构占比）——
    from app.models.d2_payments import InstitutionPurchase
    inst_purch_counts = (await db.execute(
        select(InstitutionPurchase.institution_id, func.count())
        .where(InstitutionPurchase.status == "paid")
        .group_by(InstitutionPurchase.institution_id))).all()
    inst_with_purchase = len(inst_purch_counts)
    inst_repurchased = sum(1 for _, c in inst_purch_counts if int(c) >= 2)
    inst_renewal = {
        "institutions_purchased": inst_with_purchase,
        "institutions_repurchased": inst_repurchased,
        "rate_pct": round(inst_repurchased / inst_with_purchase * 100, 1) if inst_with_purchase else 0.0,
    }

    # —— 增长分析（§5.5）：渠道来源 / 续费率 / 转化漏斗 ——
    from app.services import growth_service
    growth = await growth_service.get_growth(db)

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
            "arpu_month_yuan": arpu_month, "payers_month": payers_month,
        },
        "usage_today": usage_today,
        "active": active,
        "feedback": feedback,
        "content_quality": {
            "review_rate": review_rate,
            "ocr_success": ocr_success,
            "ocr_correction": ocr_correction,
            "practice_split": practice_split,
        },
        "growth": growth,
        "institution": {"active": inst_active, "renewal": inst_renewal},
        "generated_at": now.isoformat(),
    }
