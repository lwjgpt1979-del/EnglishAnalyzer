"""词汇「理解探针」离线批量预生成 CLI：供服务器 crontab 每晚低峰调用。

把词典里缺探针(probes_json)的词补齐,消除学生首检的 LLM 现生成等待。
词级公共缓存:所有学生共享,一词全网只生成一次;only_missing 幂等;token 预算熔断。

用法:
    DATABASE_URL=... python -m app.tasks.backfill_vocab_probes
    DATABASE_URL=... python -m app.tasks.backfill_vocab_probes --budget 300000 --limit 500
"""
import argparse
import asyncio

from app.core.database import _async_session_factory
from app.services import vocab_probe_service as vps


async def _main(budget: int, limit: int | None) -> None:
    async with _async_session_factory() as s:
        res = await vps.backfill_probes(
            s, only_missing=True, limit=limit, max_tokens_budget=budget)
        print(f"[vocab-probe-backfill] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=200_000,
                    help="本次 token 预算上限,累计超标即停(默认 20 万)")
    ap.add_argument("--limit", type=int, default=None,
                    help="最多补几个词(默认不限,跑到预算耗尽或补完)")
    args = ap.parse_args()
    asyncio.run(_main(args.budget, args.limit))
