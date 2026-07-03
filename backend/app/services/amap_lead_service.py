"""高德地图获客:官方 Web 服务「POI 文本检索」按「城市/区县 + 关键词」检索 →(可选)入库电销 CRM。

与 baidu_lead_service 同结构、同一入库适配器(source=amap)。Key 走 system_configs(运营可配)。
额度/频控用尽即停(高德 infocode 10003/10044/10019…);官方 API,非爬虫。
"""
from __future__ import annotations

import asyncio
import uuid

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SystemConfig

_KEY = "amap_config"
_URL = "https://restapi.amap.com/v3/place/text"
# 配额/频控/密钥类 infocode → 立即停(10003 日访问量超、10044 账号量超、10004/10019~10021/10029 频控、10001 key 无效)
_STOP_CODES = {"10001", "10003", "10004", "10012", "10019", "10020", "10021", "10029", "10044", "10045"}
_STOP_WORDS = ("超出", "超限", "限制", "频繁", "过期", "无效")
_MAX_PAGES = 10          # 每关键词最多翻页(offset=25/页)


async def get_key(db: AsyncSession) -> str | None:
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        return (row.value.get("key") or "").strip() or None
    return None


def mask_key(key: str | None) -> str:
    if not key:
        return ""
    return f"{key[:4]}****{key[-4:]}" if len(key) > 8 else "已设置"


async def set_key(db: AsyncSession, *, key: str, updated_by: uuid.UUID) -> None:
    key = (key or "").strip()
    row = (await db.execute(sa.select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value={"key": key},
                            description="高德地图 Web 服务 Key(获客检索用)", updated_by=updated_by))
    else:
        row.value = {**(row.value or {}), "key": key}
        row.updated_by = updated_by


def _stop_by_quota(status: object, info: object, infocode: object) -> bool:
    if str(infocode) in _STOP_CODES:
        return True
    msg = str(info or "")
    return any(w in msg for w in _STOP_WORDS)


def _clean_addr(a: object) -> str | None:
    """高德空字段可能是 []。归一为字符串或 None。"""
    if isinstance(a, list):
        return None
    s = (a or "").strip() if isinstance(a, str) else None
    return s or None


async def _fetch_kw(client: httpx.AsyncClient, key: str, keyword: str, region: str,
                    pages: int, sleep: float, max_calls: int, types: str = "") -> tuple[list[dict], bool, int]:
    """单(关键词/行业)分页检索。返回 (items, quota_hit, calls)。keyword、types 至少给一个;
    types=高德 POI 类型码或类目汉字(| 分隔多类)。max_calls 限制本次最多发几次(受每日限额)。"""
    out, seen, quota, calls = [], set(), False, 0
    for pn in range(1, min(pages, _MAX_PAGES, max(0, max_calls)) + 1):   # 高德 page 从 1 起
        params = {"city": region, "citylimit": "true", "offset": 25, "page": pn,
                  "extensions": "all", "output": "json", "key": key}
        if keyword:
            params["keywords"] = keyword
        if types:
            params["types"] = types
        calls += 1
        try:
            data = (await client.get(_URL, params=params)).json()
        except Exception:  # noqa: BLE001
            break
        if _stop_by_quota(data.get("status"), data.get("info"), data.get("infocode")):
            quota = True
            break
        if str(data.get("status")) != "1":
            break
        pois = data.get("pois") or []
        if not pois:
            break
        for p in pois:
            name = p.get("name")
            tel = _clean_addr(p.get("tel"))
            key_ = (name, tel)
            if name and key_ not in seen:
                seen.add(key_)
                out.append({"name": name, "phone": tel, "address": _clean_addr(p.get("address")),
                            "business": p.get("type"), "city": region})
        await asyncio.sleep(sleep)
    return out, quota, calls


async def fetch_leads(db: AsyncSession, *, region_name: str | None, districts: list[str] | None,
                      keywords: list[str], types: list[str] | None = None,
                      pages: int = 3, sleep: float = 0.3) -> dict:
    """按「城市 或 多个区县 ×(关键词/行业分类)」检索,跨(区县×词)去重;任一次撞额度即整体停。
    types=高德 POI 行业分类(类型码/类目汉字);关键词与行业分类至少给一个,无关键词时按行业整类捞。"""
    key = await get_key(db)
    if not key:
        raise AppError(code=400, message="未配置高德地图 Key,请先在页面「Key 设置」里填入")
    kws = [k.strip() for k in (keywords or []) if k.strip()]
    tps = "|".join(t.strip() for t in (types or []) if t.strip())
    if not kws and not tps:
        raise AppError(code=400, message="请至少填一个关键词,或选一个行业分类")
    terms = kws or [""]                              # 无关键词但有行业分类 → 空词按 types 整类检索
    regions = [d.strip() for d in (districts or []) if d.strip()] or [(region_name or "").strip()]
    regions = [r for r in regions if r]
    if not regions:
        raise AppError(code=400, message="请先选择城市(或至少一个区/县)")

    from app.services import map_usage_service as usage
    budget = await usage.remaining(db, "amap")      # 每日限额剩余;到 0 直接停
    all_items, seen, quota, daily_cap, calls = [], set(), False, budget <= 0, 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for region in regions:
            if daily_cap:
                break
            for kw in terms:
                if calls >= budget:
                    daily_cap = True
                    break
                items, q, c = await _fetch_kw(client, key, kw, region, pages, sleep, budget - calls, tps)
                calls += c
                for it in items:
                    k = (it["name"], it.get("phone"))
                    if k not in seen:
                        seen.add(k)
                        all_items.append(it)
                if q:
                    quota = True
                    break
            if quota:
                break
    if calls:
        await usage.bump(db, source="amap", n=calls)
    with_phone = sum(1 for it in all_items if (it.get("phone") or "").strip())
    return {"items": all_items, "fetched": len(all_items), "with_phone": with_phone,
            "quota_stopped": quota, "daily_cap_stopped": daily_cap, "calls": calls,
            "region": "、".join(regions)}


async def fetch_and_ingest(db: AsyncSession, *, region_name: str | None, districts: list[str] | None,
                           keywords: list[str], types: list[str] | None = None,
                           pages: int = 3, ingest: bool = False) -> dict:
    r = await fetch_leads(db, region_name=region_name, districts=districts,
                          keywords=keywords, types=types, pages=pages)
    if ingest and r["items"]:
        from datetime import datetime, timezone
        from app.services import sales_crm_service as crm
        cond = "/".join(keywords) or ("行业:" + "|".join(types or []))
        note = (f"高德地图 POI;区域={r['region']};{cond};"
                f"日期={datetime.now(timezone.utc).date()}")
        r["ingest"] = await crm.ingest_external_leads(
            db, items=r["items"], source="amap", source_note=note, require_phone=False)
    # 预览前 100 条:地址解析成 省/市/县/乡镇(与百度页一致)
    from app.services import region_service as rs
    preview = r["items"][:100]
    codes = []
    for it in preview:
        code, _ = await rs.region_from_name(db, it.get("address") or "", max_level=4)
        if not code and it.get("city"):
            code, _ = await rs.region_from_name(db, it["city"], max_level=4)
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
