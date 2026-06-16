"""增长分析（§5.5）：渠道来源分布 · 精准续费率 · 会员转化漏斗。

全部从现有表实时聚合。续费率/漏斗的口径见各函数 docstring（注明为运营近似口径）。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d2_payments import Membership, Order
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d9_system import FeatureUsage

_PAID_STATUS = ("paid", "refunded", "partial_refunded")
_CHANNEL_LABELS = {
    "school": "学校合作", "stationery": "文具店", "training": "培训机构",
    "search": "自然搜索", "referral": "老用户推荐", "other": "其他", "unknown": "未知",
}


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 1) if den else 0.0


# ── 渠道来源分布（§5.5）──────────────────────────────────────────────────────
async def channel_distribution(db: AsyncSession, *, role: str = "student") -> dict:
    """各获客渠道新增用户占比（默认仅统计学生）。空渠道归为 unknown。"""
    stmt = select(User.acquisition_channel, func.count()).group_by(User.acquisition_channel)
    if role and role != "all":
        stmt = stmt.where(User.role == role)
    rows = (await db.execute(stmt)).all()
    counts: dict[str, int] = {}
    for ch, n in rows:
        key = ch if ch in _CHANNEL_LABELS else "unknown"
        counts[key] = counts.get(key, 0) + int(n)
    total = sum(counts.values())
    items = [
        {"channel": k, "label": _CHANNEL_LABELS[k], "count": v, "pct": _pct(v, total)}
        for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]
    return {"total": total, "items": items}


# ── 精准续费率（§5.5）────────────────────────────────────────────────────────
async def renewal_rate(db: AsyncSession, *, days: int = 90) -> dict:
    """按档位续费率（近 N 天口径）。

    口径：分母 = 该档位在窗口内到期的会员数（续费机会）；
          分子 = 窗口内已支付的「续费」订单数（order_type=renew）。
    为运营近似口径（非逐会员精确匹配），rate 上限 100%。
    """
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=days)

    exp_rows = (await db.execute(
        select(Membership.tier, func.count())
        .where(and_(Membership.tier != "free",
                    Membership.expires_at.isnot(None),
                    Membership.expires_at >= start,
                    Membership.expires_at <= now))
        .group_by(Membership.tier))).all()
    expiring = {str(t): int(c) for t, c in exp_rows}

    ren_rows = (await db.execute(
        select(Order.tier, func.count())
        .where(and_(Order.order_type == "renew",
                    Order.status.in_(_PAID_STATUS),
                    Order.paid_at.isnot(None),
                    Order.paid_at >= start, Order.paid_at <= now))
        .group_by(Order.tier))).all()
    renewed = {str(t): int(c) for t, c in ren_rows}

    tiers = ["basic", "pro", "promax"]
    by_tier = []
    tot_exp = tot_ren = 0
    for t in tiers:
        e, r = expiring.get(t, 0), renewed.get(t, 0)
        tot_exp += e
        tot_ren += r
        by_tier.append({"tier": t, "expiring": e, "renewed": r,
                        "rate_pct": min(100.0, _pct(r, e))})
    return {
        "days": days,
        "overall_rate_pct": min(100.0, _pct(tot_ren, tot_exp)),
        "total_expiring": tot_exp, "total_renewed": tot_ren,
        "by_tier": by_tier,
    }


# ── 会员转化漏斗（§5.5）──────────────────────────────────────────────────────
def _min_quota_limit() -> int:
    """注册表里计量功能的最小正配额（用于判定「触达上限」）。默认 3。"""
    try:
        from app.services import entitlement_service as es
        limits = []
        for spec in es.all_features():
            for t in es.TIERS:
                rule = spec.rule_for(t)
                if getattr(rule, "mode", None) == "quota" and (rule.limit or 0) > 0:
                    limits.append(rule.limit)
        return min(limits) if limits else 3
    except Exception:
        return 3


async def funnel(db: AsyncSession) -> dict:
    """会员转化漏斗：注册 → 免费体验 → 触达次数上限 → 付费 → 续费。

    运营近似口径（全量学生，非时间切片）：
      注册      = 学生总数
      免费体验  = 有 ≥1 条错题记录的学生（完成过核心体验）
      触达上限  = feature_usage 中某计量功能用量 ≥ 最小配额阈值的用户
      付费      = 有 ≥1 笔已支付订单的受益人
      续费      = 有 ≥1 笔已支付「续费」订单的受益人
    """
    async def _count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    registered = await _count(
        select(func.count()).select_from(User).where(User.role == "student"))

    experienced = await _count(
        select(func.count(func.distinct(WrongQuestion.student_id))))

    limit = _min_quota_limit()
    hit_limit = await _count(
        select(func.count(func.distinct(FeatureUsage.user_id)))
        .where(FeatureUsage.count >= limit))

    paid = await _count(
        select(func.count(func.distinct(Order.beneficiary_id)))
        .where(Order.status.in_(_PAID_STATUS)))

    renewed = await _count(
        select(func.count(func.distinct(Order.beneficiary_id)))
        .where(and_(Order.order_type == "renew", Order.status.in_(_PAID_STATUS))))

    stages = [
        {"key": "registered", "label": "注册", "count": registered},
        {"key": "experienced", "label": "免费体验", "count": experienced},
        {"key": "hit_limit", "label": "触达次数上限", "count": hit_limit},
        {"key": "paid", "label": "付费", "count": paid},
        {"key": "renewed", "label": "续费", "count": renewed},
    ]
    # 相对注册的转化率 + 相对上一环节的转化率
    base = registered or 0
    prev = None
    for s in stages:
        s["pct_of_registered"] = _pct(s["count"], base)
        s["pct_of_prev"] = 100.0 if prev is None else _pct(s["count"], prev)
        prev = s["count"]
    return {"stages": stages}


async def get_growth(db: AsyncSession, *, renewal_days: int = 90) -> dict:
    return {
        "channels": await channel_distribution(db),
        "renewal": await renewal_rate(db, days=renewal_days),
        "funnel": await funnel(db),
    }
