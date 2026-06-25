"""语法「理解探针」离线批量预生成 CLI:供服务器 crontab 每晚低峰调用。

把语法点缺探针(grammar_probes_json)的补齐,消除学生首检的 LLM 现生成等待。
KP 级公共缓存:所有学生共享,一点全网只生成一次;only_missing 幂等;token 预算熔断。

用法:
    DATABASE_URL=... python -m app.tasks.backfill_grammar_probes
    DATABASE_URL=... python -m app.tasks.backfill_grammar_probes --budget 300000 --limit 500
"""
import argparse
import asyncio

from app.core.database import _async_session_factory
from app.services import grammar_probe_service as gp


async def _main(budget: int, limit: int | None) -> None:
    async with _async_session_factory() as s:
        res = await gp.backfill_probes(
            s, only_missing=True, limit=limit, max_tokens_budget=budget)
        print(f"[grammar-probe-backfill] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=200_000,
                    help="本次 token 预算上限,累计超标即停(默认 20 万)")
    ap.add_argument("--limit", type=int, default=None, help="最多补几个点(默认不限)")
    args = ap.parse_args()
    asyncio.run(_main(args.budget, args.limit))
