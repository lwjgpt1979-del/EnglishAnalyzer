"""生命周期自动化:跑所有 enabled 的 recurring 触达任务(增量)。供 crontab 每日调用。

用法:DATABASE_URL=... python -m app.tasks.run_reach_campaigns

每个 recurring 任务只触达「新进入分群且未被本任务触达过」的人(靠 reach_log 去重),
所以每天跑是安全的——不会重复骚扰同一用户。典型:会员7天内到期→自动站内提醒/生成线索。
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import reach_service


async def _main() -> None:
    async with _async_session_factory() as db:
        res = await reach_service.run_recurring_all(db)
    print(f"[reach-recurring] campaigns={res['campaigns']} sent={res['sent']}")
    for d in res["details"]:
        print("  -", d.get("name"), d.get("stats") or d.get("error"))


if __name__ == "__main__":
    asyncio.run(_main())
