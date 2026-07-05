"""地图获客「按区县自动采集」每日任务:供服务器 crontab 每天低峰调用。

按 system_configs.map_crawl 配置(目标省/关键词/高德类目),把百度、高德各自的
「还没采过的区县」逐个采,撞每日限额(map_usage)或第三方额度即停,次日续。
每采一个区县提交一次(断点续),挂了不会重采已采区县。

用法:
    DATABASE_URL=... python -m app.tasks.crawl_map_leads                 # 两家都跑
    DATABASE_URL=... python -m app.tasks.crawl_map_leads --source baidu  # 只跑百度
    DATABASE_URL=... python -m app.tasks.crawl_map_leads --max 1         # 每家只试跑 1 区县
"""
import argparse
import asyncio

from app.core.database import _async_session_factory
from app.services import map_crawl_service as crawl


async def _main(sources: list[str], max_districts: int | None) -> None:
    async with _async_session_factory() as s:
        for src in sources:
            res = await crawl.run_once(s, src, max_districts=max_districts)
            print(f"[map-crawl] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=list(crawl.SOURCES) + ["all"], default="all")
    ap.add_argument("--max", type=int, default=None, help="每家最多采几个区县(试跑用)")
    a = ap.parse_args()
    srcs = list(crawl.SOURCES) if a.source == "all" else [a.source]
    asyncio.run(_main(srcs, a.max))
