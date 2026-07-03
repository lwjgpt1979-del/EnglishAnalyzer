"""百度地图开放平台·地点检索(官方 Place API)拉取 POI → 标准列表 →(可选)入库电销 CRM。

仅用你自己的 AK 调**官方 API**(非网页爬虫)。注意合规:
- 百度地图 API 服务条款限制 POI 数据的批量存储/再分发,请在授权范围内、控制规模自用;
- 电销须遵守 PIPL / 工信部营销电话规,管好 consent / dnc;
- 每条落库自动写 source=baidu_map + source_note(检索词/城市/日期)。

用法:
  # 仅拉取导出 JSON(不入库)
  BAIDU_AK=你的AK python -m scripts.fetch_baidu_pois --kw 培训机构 --cities 南京,苏州 --pages 3 --out /tmp/pois.json
  # 拉取并入库(经适配器 ingest_external_leads,按 phone 去重)
  BAIDU_AK=你的AK DATABASE_URL=... python -m scripts.fetch_baidu_pois --kw 培训机构 --cities 南京 --pages 3 --ingest
"""
import argparse
import asyncio
import json
import os
import time

import httpx

_URL = "https://api.map.baidu.com/place/v2/search"


def fetch_city(ak: str, kw: str, city: str, pages: int, sleep: float) -> list[dict]:
    """单城分页检索。scope=2 返回 detail_info(含 telephone / tag)。返回标准列表。"""
    out, seen = [], set()
    with httpx.Client(timeout=20.0) as client:
        for pn in range(pages):
            params = {"query": kw, "region": city, "city_limit": "true", "scope": "2",
                      "output": "json", "page_size": 20, "page_num": pn, "ak": ak}
            try:
                data = client.get(_URL, params=params).json()
            except Exception as exc:  # noqa: BLE001
                print(f"  [{city} p{pn}] 请求失败: {exc}")
                break
            status = data.get("status")
            if status != 0:
                print(f"  [{city} p{pn}] API status={status} msg={data.get('message')}")
                break  # 常见:2=参数错 / 302,401=AK/配额问题
            results = data.get("results") or []
            if not results:
                break
            for r in results:
                di = r.get("detail_info") or {}
                item = {
                    "name": r.get("name"),
                    "phone": r.get("telephone") or di.get("telephone"),
                    "address": r.get("address"),
                    "business": di.get("tag") or di.get("classified_poi_tag"),
                    "city": city,
                }
                key = (item["name"], item.get("phone"))
                if item["name"] and key not in seen:
                    seen.add(key)
                    out.append(item)
            time.sleep(sleep)   # 尊重配额,别打太快
    print(f"  [{city}] 采集 {len(out)} 条")
    return out


async def _ingest(items: list[dict], kw: str):
    """经通用适配器入库(按 phone 去重,自动填 source/source_note)。"""
    from datetime import datetime, timezone
    from app.core.database import async_session_factory
    from app.services import sales_crm_service as crm
    note = f"百度地图 Place API;检索词={kw};日期={datetime.now(timezone.utc).date()}"
    async with async_session_factory() as db:
        res = await crm.ingest_external_leads(
            db, items=items, source="baidu_map", source_note=note, require_phone=True)
        await db.commit()
    print(f"入库结果: {res}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kw", default="培训机构", help="检索关键词")
    ap.add_argument("--cities", required=True, help="城市名逗号分隔,如 南京,苏州,无锡")
    ap.add_argument("--pages", type=int, default=3, help="每城翻页数(每页≤20)")
    ap.add_argument("--sleep", type=float, default=0.3, help="请求间隔秒")
    ap.add_argument("--out", default=None, help="导出 JSON 路径(不填则不导出)")
    ap.add_argument("--ingest", action="store_true", help="直接入库电销 CRM")
    args = ap.parse_args()

    ak = os.getenv("BAIDU_AK")
    if not ak:
        raise SystemExit("请设置环境变量 BAIDU_AK(百度地图开放平台服务端 AK)")

    all_items: list[dict] = []
    for city in [c.strip() for c in args.cities.split(",") if c.strip()]:
        all_items.extend(fetch_city(ak, args.kw, city, args.pages, args.sleep))
    print(f"合计采集 {len(all_items)} 条")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        print(f"已导出 → {args.out}")
    if args.ingest:
        asyncio.run(_ingest(all_items, args.kw))


if __name__ == "__main__":
    main()
