"""地图获客「按区县自动采集」调度:每日任务据配额把目标省的区县逐个采完。

- 目标范围可运营配置(system_configs.map_crawl):默认江苏,admin 可加省;关键词/高德类目/页数同表。
- 粒度=区县(level3):map API 的 region 参数只可靠支持到区县,乡镇会被忽略/串错(见方案)。
- frontier = 目标省下的所有区县 − 已在 map_crawl_progress 里 done/empty 的;每日任务取剩余、逐个采,
  撞「本地每日限额(map_usage)」或「第三方额度」就停,次日续。
- 每采一个区县提交一次(断点续:即使中途挂了,已采的区县不会重采)。

配置读写走 system_configs(铁律:运营可配置值不写死);常量仅兜底默认。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.models.d23_sales_crm import MapCrawlProgress
from app.services import map_usage_service as usage

_KEY = "map_crawl"
SOURCES = ("baidu", "amap")

# 兜底默认(实际值以 system_configs.map_crawl 为准,本常量仅配置缺失时兜底)
DEFAULTS: dict = {
    "enabled": False,                 # 默认关;admin 开启后 cron 才会真采
    "provinces": ["32"],              # 目标省 level1 码;默认江苏(译林版主区域)
    "keywords": ["英语培训", "培训机构", "辅导班"],
    "amap_types": ["141400"],         # 高德 POI 类目码:141400=培训机构(百度走 keywords)
    "pages": 3,                       # 每(区县×词)翻页数
}


# ---------------- 配置 ----------------
async def _cfg_row(db: AsyncSession) -> SystemConfig | None:
    return (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()


async def get_config(db: AsyncSession) -> dict:
    row = await _cfg_row(db)
    cfg = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        for k in DEFAULTS:
            if k in row.value and row.value[k] is not None:
                cfg[k] = row.value[k]
    cfg["provinces"] = [str(p) for p in (cfg.get("provinces") or []) if str(p).strip()]
    cfg["keywords"] = [str(k).strip() for k in (cfg.get("keywords") or []) if str(k).strip()]
    cfg["amap_types"] = [str(t).strip() for t in (cfg.get("amap_types") or []) if str(t).strip()]
    cfg["pages"] = max(1, min(int(cfg.get("pages") or 3), 10))
    cfg["enabled"] = bool(cfg.get("enabled"))
    return cfg


async def set_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID | None) -> dict:
    """局部更新配置(只覆盖传入的键)。并发安全:先幂等建行再更新。"""
    await db.execute(
        pg_insert(SystemConfig)
        .values(id=uuid.uuid4(), key=_KEY, value=dict(DEFAULTS),
                description="地图获客·按区县自动采集配置(目标省/关键词/高德类目/页数/开关)")
        .on_conflict_do_nothing(index_elements=["key"]))
    await db.flush()
    row = await _cfg_row(db)
    val = dict(row.value or {})
    for k in ("enabled", "provinces", "keywords", "amap_types", "pages"):
        if k in patch and patch[k] is not None:
            val[k] = patch[k]
    row.value = val
    if updated_by is not None:
        row.updated_by = updated_by
    await db.flush()
    return await get_config(db)


# ---------------- frontier / 进度 ----------------
async def _all_districts(db: AsyncSession, provinces: list[str]) -> list[dict]:
    """目标省下的所有区县(level3),带所属市名。provinces=省 level1 码列表。"""
    if not provinces:
        return []
    from app.models.d21_region import Region        # 局部导入避免循环
    conds = [Region.code.like(p[:2] + "%") for p in provinces]
    rows = (await db.execute(
        sa.select(Region.code, Region.name, Region.parent_code)
        .where(Region.level == 3, sa.or_(*conds))
        .order_by(Region.code))).all()
    # 市名(level2)一次查全
    city_codes = {r.parent_code for r in rows if r.parent_code}
    cities = {}
    if city_codes:
        crows = (await db.execute(
            sa.select(Region.code, Region.name).where(Region.code.in_(city_codes)))).all()
        cities = {c.code: c.name for c in crows}
    return [{"code": r.code, "name": r.name, "city_name": cities.get(r.parent_code)}
            for r in rows]


async def _done_codes(db: AsyncSession, source: str) -> set[str]:
    """已采过(done/empty)的区县码——error 的可重试,不算已采。"""
    rows = (await db.execute(
        sa.select(MapCrawlProgress.region_code).where(
            MapCrawlProgress.source == source,
            MapCrawlProgress.status.in_(("done", "empty"))))).all()
    return {r.region_code for r in rows}


async def pending_districts(db: AsyncSession, source: str) -> list[dict]:
    cfg = await get_config(db)
    done = await _done_codes(db, source)
    return [d for d in await _all_districts(db, cfg["provinces"]) if d["code"] not in done]


async def progress(db: AsyncSession) -> dict:
    """每源覆盖进度 {baidu:{total,done,empty,error,pending,fetched,ingested}, amap:{...}}。"""
    cfg = await get_config(db)
    total = len(await _all_districts(db, cfg["provinces"]))
    out: dict = {"provinces": cfg["provinces"], "enabled": cfg["enabled"]}
    for s in SOURCES:
        rows = (await db.execute(
            sa.select(MapCrawlProgress.status, sa.func.count(),
                      sa.func.coalesce(sa.func.sum(MapCrawlProgress.fetched), 0),
                      sa.func.coalesce(sa.func.sum(MapCrawlProgress.ingested), 0))
            .where(MapCrawlProgress.source == s)
            .group_by(MapCrawlProgress.status))).all()
        by = {r[0]: {"n": r[1], "fetched": int(r[2]), "ingested": int(r[3])} for r in rows}
        done = by.get("done", {}).get("n", 0)
        empty = by.get("empty", {}).get("n", 0)
        err = by.get("error", {}).get("n", 0)
        out[s] = {
            "total": total, "done": done, "empty": empty, "error": err,
            "pending": max(0, total - done - empty),
            "fetched": sum(v["fetched"] for v in by.values()),
            "ingested": sum(v["ingested"] for v in by.values()),
        }
    return out


# ---------------- 采集一轮 ----------------
async def _mark(db: AsyncSession, source: str, d: dict, *, status: str,
                fetched: int = 0, ingested: int = 0, error: str | None = None) -> None:
    """幂等 upsert 进度行(区县可能之前是 error,这次重试成功要覆盖)。"""
    stmt = pg_insert(MapCrawlProgress).values(
        source=source, region_code=d["code"], region_name=d["name"],
        city_name=d.get("city_name"), status=status,
        fetched=fetched, ingested=ingested, error=error)
    await db.execute(stmt.on_conflict_do_update(
        index_elements=["source", "region_code"],
        set_={"region_name": d["name"], "city_name": d.get("city_name"),
              "status": status, "fetched": fetched, "ingested": ingested,
              "error": error, "fetched_at": sa.func.now()}))


async def run_once(db: AsyncSession, source: str, *, max_districts: int | None = None,
                   respect_enabled: bool = True) -> dict:
    """把 source 的未采区县逐个采,直到:撞每日限额 / 撞第三方额度 / 采完 / 到 max_districts。

    每个区县单独 commit(断点续)。返回本轮汇总。max_districts 供「手动试跑一个」。
    """
    if source not in SOURCES:
        raise ValueError(f"未知来源:{source}")
    cfg = await get_config(db)
    if respect_enabled and not cfg["enabled"]:
        return {"source": source, "skipped": "disabled", "districts_done": 0}

    from app.services import baidu_lead_service as baidu
    from app.services import amap_lead_service as amap

    pend = await pending_districts(db, source)
    if max_districts is not None:
        pend = pend[:max_districts]

    done_n = fetched_n = ingested_n = 0
    stopped: str | None = None
    for d in pend:
        if await usage.remaining(db, source) <= 0:
            stopped = "daily_cap"
            break
        try:
            if source == "baidu":
                r = await baidu.fetch_and_ingest(
                    db, region_name=d.get("city_name"), districts=[d["name"]],
                    keywords=cfg["keywords"], pages=cfg["pages"], ingest=True)
            else:
                r = await amap.fetch_and_ingest(
                    db, region_name=d.get("city_name"), districts=[d["name"]],
                    keywords=cfg["keywords"], types=cfg["amap_types"] or None,
                    pages=cfg["pages"], ingest=True)
        except Exception as e:  # noqa: BLE001 单区县出错标 error、继续下一个
            await db.rollback()
            await _mark(db, source, d, status="error", error=str(e)[:300])
            await db.commit()
            continue

        if r.get("quota_stopped"):
            # 第三方额度中途耗尽:本区县不完整 → 不标 done,留待次日重采
            await db.commit()          # usage.bump 已在 fetch 内发生,提交保住计数
            stopped = "quota"
            break

        ing = int((r.get("ingest") or {}).get("created", 0))
        await _mark(db, source, d,
                    status=("empty" if r.get("fetched", 0) == 0 else "done"),
                    fetched=int(r.get("fetched", 0)), ingested=ing)
        await db.commit()
        done_n += 1
        fetched_n += int(r.get("fetched", 0))
        ingested_n += ing
        if r.get("daily_cap_stopped"):
            stopped = "daily_cap"
            break

    return {"source": source, "districts_done": done_n, "fetched": fetched_n,
            "ingested": ingested_n, "stopped": stopped, "remaining_pending": len(pend) - done_n}
