"""权益体系（feature entitlements）。

核心思想：模块声明「能力键」(module.capability)，档位授予能力。门禁统一收口。
- 注册表(代码默认，扩展点)：新模块 register_feature 即生效、自动进 /me/entitlements 与后台配置。
- 覆盖表 feature_overrides(运营按 key+tier 覆盖 allow/quota，不发版可调)。
- 配额表 feature_usage(计量功能按周期计数)。

步骤1：只建地基，不改任何现有门禁行为（不被现有接口调用即不影响线上）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError

TIERS = ["free", "basic", "pro", "promax"]
_TIER_RANK = {t: i for i, t in enumerate(TIERS)}


# ── 规则与能力声明 ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Rule:
    mode: str                      # allow / deny / quota
    limit: int | None = None       # quota 模式下的次数上限
    period: str | None = None      # day / month

    def to_dict(self) -> dict:
        return {"mode": self.mode, "limit": self.limit, "period": self.period}


def ALLOW() -> Rule:
    return Rule("allow")


def DENY() -> Rule:
    return Rule("deny")


def QUOTA(limit: int, period: str = "month") -> Rule:
    return Rule("quota", limit, period)


@dataclass
class FeatureSpec:
    key: str
    title: str
    module: str
    by_tier: dict                  # tier -> Rule（缺省按 _fallback）
    condition: str | None = None   # 例：'purchased_semester'（与档位正交）
    _fallback: Rule = field(default_factory=DENY)

    def rule_for(self, tier: str) -> Rule:
        return self.by_tier.get(tier, self._fallback)


# ── 注册表（默认值；新模块在此追加，或运行时 register_feature）────────────────────
_FEATURES: dict[str, FeatureSpec] = {}


def register_feature(spec: FeatureSpec) -> None:
    _FEATURES[spec.key] = spec


def all_features() -> list[FeatureSpec]:
    return list(_FEATURES.values())


def get_feature(key: str) -> FeatureSpec | None:
    return _FEATURES.get(key)


def _all_allow() -> dict:
    return {t: ALLOW() for t in TIERS}


def _paid_allow() -> dict:
    return {"free": DENY(), "basic": ALLOW(), "pro": ALLOW(), "promax": ALLOW()}


def _seed_defaults() -> None:
    F = register_feature
    # 词力通
    F(FeatureSpec("vocab.study", "词力通学习/测试", "vocab", _all_allow()))
    F(FeatureSpec("vocab.report", "词力通学情报表", "vocab", _all_allow()))
    F(FeatureSpec("vocab.shadow", "词力通跟读评测", "vocab", _paid_allow()))
    # 口语
    F(FeatureSpec("speaking.dialogue", "AI口语对话", "speaking", _paid_allow()))
    F(FeatureSpec("speaking.coach", "口语陪练点评", "speaking",
                  {"free": DENY(), "basic": DENY(), "pro": ALLOW(), "promax": ALLOW()}))
    # 作文
    F(FeatureSpec("essay.prompts", "作文题库/审题", "essay", _all_allow()))
    F(FeatureSpec("essay.diagnose", "作文按档诊断", "essay",
                  {"free": DENY(), "basic": DENY(), "pro": QUOTA(3, "month"), "promax": ALLOW()}))
    F(FeatureSpec("essay.polish", "作文精修", "essay",
                  {"free": DENY(), "basic": DENY(), "pro": QUOTA(3, "month"), "promax": ALLOW()}))
    F(FeatureSpec("essay.rewrite", "作文多轮重写", "essay",
                  {"free": DENY(), "basic": DENY(), "pro": DENY(), "promax": ALLOW()}))
    # 课程（与档位正交：需购买对应学期）
    F(FeatureSpec("curriculum.unit", "教材单元", "curriculum", _all_allow(),
                  condition="purchased_semester"))


_seed_defaults()


# ── 覆盖合并 ───────────────────────────────────────────────────────────────────
async def _overrides_for(db: AsyncSession, key: str) -> dict:
    rows = (await db.execute(text(
        "SELECT tier, mode, quota_limit, quota_period FROM feature_overrides WHERE feature_key=:k"
    ), {"k": key})).all()
    out = {}
    for tier, mode, lim, period in rows:
        out[tier] = Rule(mode, lim, period)
    return out


async def effective_rule(db: AsyncSession, *, key: str, tier: str) -> Rule:
    spec = _FEATURES.get(key)
    if spec is None:
        return DENY()
    ov = await _overrides_for(db, key)
    return ov.get(tier) or spec.rule_for(tier)


def _required_tiers(spec: FeatureSpec, overrides_by_tier: dict | None = None) -> list[str]:
    ov = overrides_by_tier or {}
    out = []
    for t in TIERS:
        r = ov.get(t) or spec.rule_for(t)
        if r.mode != "deny":
            out.append(t)
    return out


# ── 配额计数 ───────────────────────────────────────────────────────────────────
def _bucket(period: str | None) -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d") if period == "day" else now.strftime("%Y-%m")


async def _usage_count(db: AsyncSession, *, user_id, key: str, period: str | None) -> int:
    b = _bucket(period)
    row = (await db.execute(text(
        "SELECT count FROM feature_usage WHERE user_id=:u AND feature_key=:k AND period_bucket=:b"
    ), {"u": str(user_id), "k": key, "b": b})).first()
    return int(row[0]) if row else 0


async def consume(db: AsyncSession, *, user_id, key: str) -> None:
    """计量功能成功执行后调用，按周期 +1（与业务同事务）。"""
    spec = _FEATURES.get(key)
    period = None
    # 取该用户档位下的 period（quota 模式才有意义）；这里按 spec 默认 period 兜底
    for t in TIERS:
        r = spec.rule_for(t) if spec else DENY()
        if r.mode == "quota" and r.period:
            period = r.period
            break
    b = _bucket(period)
    await db.execute(pg_insert_usage(user_id, key, b))


def pg_insert_usage(user_id, key, bucket):
    from app.models.d9_system import FeatureUsage  # 延迟导入避免环
    stmt = pg_insert(FeatureUsage).values(
        id=uuid.uuid4(), user_id=user_id, feature_key=key, period_bucket=bucket, count=1
    ).on_conflict_do_update(
        index_elements=["user_id", "feature_key", "period_bucket"],
        set_={"count": FeatureUsage.count + 1, "updated_at": datetime.now(timezone.utc)},
    )
    return stmt


# ── 校验 ───────────────────────────────────────────────────────────────────────
async def _tier_of(db: AsyncSession, user_id) -> str:
    from app.services import membership_service
    m = await membership_service.get_active_membership(db, user_id=user_id)
    return str(m.tier) if m else "free"


async def check(db: AsyncSession, *, user_id, key: str, tier: str | None = None,
                ctx: dict | None = None) -> dict:
    """返回 {key, allowed, mode, quota_limit, quota_left, required_tiers, condition, reason}。"""
    spec = _FEATURES.get(key)
    if spec is None:
        return {"key": key, "allowed": False, "mode": "deny", "reason": "未注册的能力"}
    tier = tier or await _tier_of(db, user_id)
    ov = await _overrides_for(db, key)
    rule = ov.get(tier) or spec.rule_for(tier)
    req = _required_tiers(spec, ov)

    quota_limit = quota_left = None
    if rule.mode == "quota":
        used = await _usage_count(db, user_id=user_id, key=key, period=rule.period)
        quota_limit = rule.limit
        quota_left = max(0, (rule.limit or 0) - used)
        allowed = quota_left > 0
        reason = "" if allowed else f"本周期次数已用完（{rule.limit}/{rule.period}）"
    elif rule.mode == "allow":
        allowed, reason = True, ""
    else:
        allowed, reason = False, "当前档位不可用"

    # 条件（与档位正交）：例如需购买学期
    condition_met = None
    if allowed and spec.condition == "purchased_semester":
        condition_met = bool((ctx or {}).get("purchased", False)) if ctx else None
        if ctx is not None and not condition_met:
            allowed, reason = False, "需购买对应学期后解锁"

    return {
        "key": key, "title": spec.title, "module": spec.module,
        "allowed": allowed, "mode": rule.mode,
        "quota_limit": quota_limit, "quota_left": quota_left,
        "required_tiers": req, "condition": spec.condition,
        "condition_met": condition_met, "reason": reason,
    }


async def require_feature(db: AsyncSession, *, user_id, key: str, ctx: dict | None = None,
                          code: int = 403, message: str | None = None) -> dict:
    """门禁：不可用则抛 AppError。返回 check 结果（调用方成功后可 consume）。

    code/message 可覆盖，用于迁移期保留各处原有的错误码与文案（前端不变）。
    """
    res = await check(db, user_id=user_id, key=key, ctx=ctx)
    if not res.get("allowed"):
        if message is None:
            tiers = "/".join(res.get("required_tiers") or []) or "更高档位"
            message = res.get("reason") or f"该功能需 {tiers} 会员"
        raise AppError(code=code, message=message)
    return res


async def me_entitlements(db: AsyncSession, *, user_id) -> dict:
    """该用户对所有已注册能力的有效结果图（前端做锁标/配额/弹墙）。"""
    tier = await _tier_of(db, user_id)
    out = {}
    for spec in _FEATURES.values():
        out[spec.key] = await check(db, user_id=user_id, key=spec.key, tier=tier)
    return {"tier": tier, "features": out}


# ── 后台配置 ───────────────────────────────────────────────────────────────────
async def admin_list(db: AsyncSession) -> dict:
    """注册表全集 + 当前覆盖（供后台可视化配置）。"""
    items = []
    for spec in _FEATURES.values():
        ov = await _overrides_for(db, spec.key)
        items.append({
            "key": spec.key, "title": spec.title, "module": spec.module,
            "condition": spec.condition,
            "defaults": {t: spec.rule_for(t).to_dict() for t in TIERS},
            "overrides": {t: r.to_dict() for t, r in ov.items()},
        })
    return {"tiers": TIERS, "features": items}


async def admin_set_override(db: AsyncSession, *, key: str, tier: str, mode: str,
                             limit: int | None, period: str | None, updated_by) -> None:
    if key not in _FEATURES:
        raise AppError(code=404, message="未注册的能力")
    if tier not in TIERS:
        raise AppError(code=400, message="无效档位")
    if mode not in ("allow", "deny", "quota"):
        raise AppError(code=400, message="无效模式")
    await db.execute(text(
        "INSERT INTO feature_overrides(id,feature_key,tier,mode,quota_limit,quota_period,updated_by,updated_at) "
        "VALUES(:id,:k,:t,:m,:l,:p,:by,now()) "
        "ON CONFLICT(feature_key,tier) DO UPDATE SET mode=:m,quota_limit=:l,quota_period=:p,updated_by=:by,updated_at=now()"
    ), {"id": str(uuid.uuid4()), "k": key, "t": tier, "m": mode, "l": limit,
        "p": period, "by": str(updated_by) if updated_by else None})


async def admin_clear_override(db: AsyncSession, *, key: str, tier: str) -> None:
    await db.execute(text(
        "DELETE FROM feature_overrides WHERE feature_key=:k AND tier=:t"
    ), {"k": key, "t": tier})
