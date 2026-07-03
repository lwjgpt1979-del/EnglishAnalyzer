"""百度地图获客:官方 Place API 按「省市 + 区县 + 关键词」检索 POI → 标准列表 →(可选)入库电销 CRM。

- 仅用运营配置的 AK 调**官方 API**(非网页爬虫)。AK 走 system_configs(CLAUDE.md 铁律:运营可配)。
- **额度用尽即停**:百度返回配额/权限类 status(302/401/240…)或 message 含「配额/超限/频繁」→ 立即停,
  返回 quota_stopped=True,不再空耗。
- 入库经 sales_crm_service.ingest_external_leads(按 phone 去重、自动填 source=baidu_map + source_note)。
- 合规:每条 source_note 记「区域/关键词/日期」;电销守 PIPL/营销规,用好 consent/dnc。
"""
from __future__ import annotations

import asyncio
import uuid

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SystemConfig

_KEY = "baidu_map_config"
_URL = "https://api.map.baidu.com/place/v2/search"
# 配额/权限/频控类 status → 立即停(302 天配额超限、401 频繁、240/4 无权限、210/211 来源未授权)
_STOP_STATUS = {302, 401, 240, 4, 210, 211}
_STOP_WORDS = ("配额", "超限", "频繁", "quota", "limit", "denied", "无权限")
_MAX_PAGES = 10          # 每关键词最多翻页(每页≤20;百度检索也就 ~200 条上限)


async def get_ak(db: AsyncSession) -> str | None:
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        return (row.value.get("ak") or "").strip() or None
    return None


def mask_ak(ak: str | None) -> str:
    if not ak:
        return ""
    return f"{ak[:4]}****{ak[-4:]}" if len(ak) > 8 else "已设置"


async def set_ak(db: AsyncSession, *, ak: str, updated_by: uuid.UUID) -> None:
    ak = (ak or "").strip()
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value={"ak": ak},
                            description="百度地图开放平台服务端 AK(获客检索用)", updated_by=updated_by))
    else:
        row.value = {**(row.value or {}), "ak": ak}
        row.updated_by = updated_by


def _stop_by_quota(status: object, message: object) -> bool:
    if status in _STOP_STATUS:
        return True
    msg = str(message or "")
    return any(w in msg for w in _STOP_WORDS)


async def _fetch_kw(client: httpx.AsyncClient, ak: str, keyword: str, region: str,
                    pages: int, sleep: float, max_calls: int) -> tuple[list[dict], bool, int]:
    """单关键词分页检索。返回 (items, quota_hit, calls)。max_calls 限制本词最多发几次(受每日限额)。"""
    out, seen, quota, calls = [], set(), False, 0
    for pn in range(min(pages, _MAX_PAGES, max(0, max_calls))):
        params = {"query": keyword, "region": region, "city_limit": "true", "scope": "2",
                  "output": "json", "page_size": 20, "page_num": pn, "ak": ak}
        calls += 1
        try:
            data = (await client.get(_URL, params=params)).json()
        except Exception:  # noqa: BLE001 — 网络/解析异常:停该词,不连累其它
            break
        if _stop_by_quota(data.get("status"), data.get("message")):
            quota = True
            break
        if data.get("status") != 0:
            break
        results = data.get("results") or []
        if not results:
            break
        for r in results:
            di = r.get("detail_info") or {}
            name = r.get("name")
            phone = r.get("telephone") or di.get("telephone")
            key = (name, phone)
            if name and key not in seen:
                seen.add(key)
                out.append({"name": name, "phone": phone, "address": r.get("address"),
                            "business": di.get("tag") or di.get("classified_poi_tag"), "city": region})
        await asyncio.sleep(sleep)
    return out, quota, calls


async def fetch_leads(db: AsyncSession, *, region_name: str | None, districts: list[str] | None,
                      keywords: list[str], pages: int = 3, sleep: float = 0.3) -> dict:
    """按「城市 或 多个区县 × 多关键词」检索,跨(区县×词)去重;任一次撞额度即整体停。"""
    ak = await get_ak(db)
    if not ak:
        raise AppError(code=400, message="未配置百度地图 AK,请先在页面「AK 设置」里填入")
    kws = [k.strip() for k in (keywords or []) if k.strip()]
    if not kws:
        raise AppError(code=400, message="请至少填一个关键词")
    # 选了区县 → 逐个区县检索;没选 → 整市。区域名传给百度 region。
    regions = [d.strip() for d in (districts or []) if d.strip()] or [(region_name or "").strip()]
    regions = [r for r in regions if r]
    if not regions:
        raise AppError(code=400, message="请先选择城市(或至少一个区/县)")

    from app.services import map_usage_service as usage
    budget = await usage.remaining(db, "baidu")     # 每日限额剩余;到 0 直接停
    all_items, seen, quota, daily_cap, calls = [], set(), False, budget <= 0, 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for region in regions:
            if daily_cap:
                break
            for kw in kws:
                if calls >= budget:
                    daily_cap = True
                    break
                items, q, c = await _fetch_kw(client, ak, kw, region, pages, sleep, budget - calls)
                calls += c
                for it in items:
                    key = (it["name"], it.get("phone"))
                    if key not in seen:
                        seen.add(key)
                        all_items.append(it)
                if q:
                    quota = True
                    break
            if quota:                 # 额度到 → 停整轮
                break
    if calls:
        await usage.bump(db, source="baidu", n=calls)
    with_phone = sum(1 for it in all_items if (it.get("phone") or "").strip())
    return {"items": all_items, "fetched": len(all_items), "with_phone": with_phone,
            "quota_stopped": quota, "daily_cap_stopped": daily_cap, "calls": calls,
            "region": "、".join(regions)}


async def fetch_and_ingest(db: AsyncSession, *, region_name: str | None, districts: list[str] | None,
                           keywords: list[str], pages: int, ingest: bool) -> dict:
    r = await fetch_leads(db, region_name=region_name, districts=districts, keywords=keywords, pages=pages)
    if ingest and r["items"]:
        from datetime import datetime, timezone
        from app.services import sales_crm_service as crm
        note = (f"百度地图 Place API;区域={r['region']};关键词={'/'.join(keywords)};"
                f"日期={datetime.now(timezone.utc).date()}")
        r["ingest"] = await crm.ingest_external_leads(
            db, items=r["items"], source="baidu_map", source_note=note, require_phone=False)
    # 预览只回前 100 条;逐条把地址解析成 省/市/县/乡镇(走 region 表 max_level=4)供展示
    from app.services import region_service as rs
    preview = r["items"][:100]
    # 基准:检索的市(region_name 是地级市名,一定能解析到市级)——地址解不出时兜底省/市
    base_code, _ = await rs.region_from_name(db, region_name or "", max_level=2)
    codes: list[str | None] = []
    for it in preview:
        # 优先按百度地址解析(通常带全「省市区镇」);解不出再用「市名+该POI检索区县名」上下文
        code, _ = await rs.region_from_name(db, it.get("address") or "", max_level=4)
        if not code:
            ctx = (region_name or "") + (it.get("city") or "")
            if ctx:
                code, _ = await rs.region_from_name(db, ctx, max_level=4)
        code = code or base_code
        it["_rc"] = code
        codes.append(code)
    bd = await rs.region_breakdowns(db, codes)
    for it in preview:
        b = bd.get(it.pop("_rc", None)) or {}
        it["region_province"] = b.get("province")
        it["region_city"] = b.get("city")
        it["region_district"] = b.get("district")
        it["region_town"] = b.get("town")
    r["preview"] = preview
    r.pop("items", None)
    return r
