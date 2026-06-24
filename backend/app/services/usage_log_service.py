"""LLM 用量台账 + 批量预算熔断。

- note():每次真实 LLM 调用后记一行(token/模型/用途/finish_reason),并累加当前预算域的已花 token。
  写库失败只告警、绝不影响主调用。
- budget()/over_budget():批量任务(抽取/回填)包一层预算域,逐条作答后查是否超预算,超了就停。
- summary():后台聚合(总量 + 按用途/模型/天),按价目表估算成本。
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import logging
import uuid
from contextvars import ContextVar

import sqlalchemy as sa

from app.core.config import settings
from app.core.database import async_session_factory

_log = logging.getLogger(__name__)

LOW_BALANCE_THRESHOLD = 10.0   # 余额低于此值(元)后台告警


async def fetch_balance() -> dict:
    """查 DeepSeek 账户余额(GET /user/balance,只读不计费)。
    返回 {ok, available, currency, total, granted, topped_up, low} 或 {ok:False, reason}。"""
    from app.services.llm_provider import is_llm_dev_mode
    if is_llm_dev_mode():
        return {"ok": False, "reason": "dev-mock(占位 key),无真实余额"}
    base = settings.llm_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/user/balance"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
            r.raise_for_status()
            d = r.json()
        info = (d.get("balance_infos") or [{}])[0]
        total = float(info.get("total_balance") or 0)
        return {"ok": True, "available": bool(d.get("is_available")),
                "currency": info.get("currency") or "CNY", "total": total,
                "granted": float(info.get("granted_balance") or 0),
                "topped_up": float(info.get("topped_up_balance") or 0),
                "low": (not d.get("is_available")) or total < LOW_BALANCE_THRESHOLD,
                "threshold": LOW_BALANCE_THRESHOLD}
    except Exception as exc:  # noqa: BLE001
        _log.warning("fetch_balance failed: %s", exc)
        return {"ok": False, "reason": "查询失败(余额接口仅 DeepSeek 支持,或网络/密钥问题)"}

# 每百万 token 估算单价(元);deepseek-v4-pro 为推理档、deepseek-chat 为非推理档。
# 注:为估算值,请按 DeepSeek 账单实际单价调整。(input, output)
_PRICES: dict[str, tuple[float, float]] = {
    "deepseek-v4-pro": (2.0, 8.0),
    "deepseek-chat": (1.0, 4.0),
}
_PRICE_DEFAULT = (2.0, 8.0)


def price_of(model: str) -> tuple[float, float]:
    return _PRICES.get(model, _PRICE_DEFAULT)


def est_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = price_of(model)
    return round((prompt_tokens * pin + completion_tokens * pout) / 1_000_000, 6)


# ── 预算熔断(contextvar,按任务域累计已花 token)──────────────────────
_spent: ContextVar[int] = ContextVar("llm_spent", default=0)
_budget: ContextVar[int | None] = ContextVar("llm_budget", default=None)


@contextlib.contextmanager
def budget(max_total_tokens: int | None):
    """开一个预算域:域内所有 LLM 调用累计 token;配合 over_budget() 在批量循环里熔断。"""
    t_spent = _spent.set(0)
    t_budget = _budget.set(max_total_tokens)
    try:
        yield
    finally:
        _spent.reset(t_spent)
        _budget.reset(t_budget)


def add_spent(tokens: int) -> None:
    _spent.set(_spent.get() + max(0, tokens))


def spent() -> int:
    return _spent.get()


def over_budget() -> bool:
    b = _budget.get()
    return b is not None and _spent.get() >= b


async def note(*, model: str, feature: str, prompt_tokens: int,
               completion_tokens: int, finish_reason: str | None) -> None:
    """记一次用量:累加预算 + 落台账(失败只告警)。"""
    add_spent((prompt_tokens or 0) + (completion_tokens or 0))
    try:
        from app.models.d9_system import LlmUsageLog
        async with async_session_factory() as db:
            db.add(LlmUsageLog(
                id=uuid.uuid4(), model=model, feature=feature,
                prompt_tokens=prompt_tokens or 0, completion_tokens=completion_tokens or 0,
                finish_reason=finish_reason))
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning("usage note failed: %s", exc)


async def summary(db, *, days: int = 30) -> dict:
    """后台用量汇总:近 days 天的总量 + 按用途/模型/天,附成本估算(元)。"""
    from app.models.d9_system import LlmUsageLog
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    P, C = LlmUsageLog.prompt_tokens, LlmUsageLog.completion_tokens

    async def grouped(col):
        rows = (await db.execute(
            sa.select(col, sa.func.count().label("calls"),
                      sa.func.coalesce(sa.func.sum(P), 0).label("pin"),
                      sa.func.coalesce(sa.func.sum(C), 0).label("pout"))
            .where(LlmUsageLog.created_at >= since).group_by(col).order_by(col))).all()
        return rows

    by_model = [{"model": m, "calls": calls, "prompt_tokens": pin, "completion_tokens": pout,
                 "cost": est_cost(m, pin, pout)} for m, calls, pin, pout in await grouped(LlmUsageLog.model)]
    by_feature = []
    for f, calls, pin, pout in await grouped(LlmUsageLog.feature):
        # 用途成本按各模型分摊不易,简单用默认价估;模型维度的 cost 更准
        by_feature.append({"feature": f, "calls": calls, "prompt_tokens": pin,
                           "completion_tokens": pout})
    day_col = sa.func.date(LlmUsageLog.created_at)
    by_day = [{"day": str(d), "calls": calls, "prompt_tokens": pin, "completion_tokens": pout}
              for d, calls, pin, pout in await grouped(day_col)]

    total_calls = sum(m["calls"] for m in by_model)
    total_in = sum(m["prompt_tokens"] for m in by_model)
    total_out = sum(m["completion_tokens"] for m in by_model)
    total_cost = round(sum(m["cost"] for m in by_model), 4)
    return {
        "days": days, "total_calls": total_calls, "total_prompt_tokens": total_in,
        "total_completion_tokens": total_out, "est_cost": total_cost,
        "by_model": by_model, "by_feature": by_feature, "by_day": by_day,
        "prices": {m: {"in_per_m": p[0], "out_per_m": p[1]} for m, p in _PRICES.items()},
    }
