"""地区↔英语教材版本 对应(以初中英语为主)。

数据源=公开信息整理,**各地由地市教育局自定教材**,故一律「省级默认 + 可人工校对 + 地市例外」:
- seed_defaults 按省灌省级默认(verified=False,待校对);
- 地市/区县有差异时,admin 按 4/6 位码另加一行覆盖(优先级更高);
- textbook_for(code) 从精确码逐级上溯(区县→市→省)取最近一条命中。

省级默认见 _PROVINCE_DEFAULTS(键=省名子串);注释标明主流版本+常见地市差异。
铁律:该映射运营可改(admin CRUD),代码里的默认仅首次 seed 用,之后以库为准。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d21_region import Region, RegionTextbook

# 已知英语教材版本白名单(admin 下拉备选;可自定义扩展)
KNOWN_VERSIONS = [
    "人教版", "译林版", "外研版", "北师大版", "冀教版", "鲁教版(五四制)",
    "沪教版(牛津上海)", "新世纪版(上海)", "仁爱版", "闽教版", "湘少版", "陕旅版",
    "科普版", "牛津深圳版", "教科版(广州)",
]

# 省级默认(初中英语主流版本 + 常见地市差异)。键=省名子串,匹配 region.level==1 的 name。
# ⚠ 均为待校对默认:各地市可自定,精确到地市请在 admin 加覆盖行。
_PROVINCE_DEFAULTS: dict[str, tuple[list[str], str]] = {
    "北京": (["人教版"], "部分区用外研版/北师大版"),
    "天津": (["外研版"], "部分学校人教版"),
    "河北": (["人教版", "冀教版"], "小学冀教(一/三起点)与人教PEP混;初中主人教,2025春起部分市引入冀教版初中"),
    "山西": (["人教版", "外研版"], "多地市外研版"),
    "内蒙古": (["人教版", "外研版"], ""),
    "辽宁": (["人教版", "外研版"], "大连等地外研版"),
    "吉林": (["人教版"], ""),
    "黑龙江": (["人教版"], ""),
    "上海": (["沪教版(牛津上海)"], "全市统一牛津上海版"),
    "江苏": (["译林版"], "全省统一译林版"),
    "浙江": (["人教版", "外研版"], "杭州/宁波/绍兴/台州/舟山多人教,其余多外研"),
    "安徽": (["人教版"], "部分地市仁爱版"),
    "福建": (["仁爱版", "人教版"], "初中仁爱版(厦门=人教,已锁);小学闽教/人教PEP/外研/北师大按市混"),
    "江西": (["人教版"], ""),
    "山东": (["人教版", "外研版", "鲁教版(五四制)"], "六三制区主人教/外研(小学部分鲁科);五四制整市烟台/淄博/东营/泰安/威海用鲁教版(已锁),济宁任城/济南莱芜钢城等亦五四制"),
    "河南": (["人教版", "外研版"], ""),
    "湖北": (["人教版", "仁爱版"], "多地市仁爱版"),
    "湖南": (["人教版"], "小学多湘少版"),
    "广东": (["人教版", "牛津深圳版"], "深圳沪教牛津/深港(已锁牛津深圳版)、广州广州版+沪教牛津;其余市人教/仁爱/外研混"),
    "广西": (["人教版", "外研版"], ""),
    "海南": (["人教版"], ""),
    "重庆": (["人教版", "仁爱版"], ""),
    "四川": (["人教版", "外研版"], ""),
    "贵州": (["人教版"], ""),
    "云南": (["人教版"], "部分地市北师大版"),
    "西藏": (["人教版"], ""),
    "陕西": (["人教版"], "小学多陕旅版"),
    "甘肃": (["人教版"], ""),
    "青海": (["人教版"], ""),
    "宁夏": (["人教版"], ""),
    "新疆": (["人教版"], ""),
}


async def seed_defaults(db: AsyncSession, *, overwrite: bool = False) -> dict:
    """按省灌省级默认。overwrite=False 时只补缺(不动已存在/已校对的行)。"""
    provs = (await db.execute(
        sa.select(Region.code, Region.name).where(Region.level == 1))).all()
    inserted = skipped = 0
    for code, name in provs:
        hit = next((v for k, v in _PROVINCE_DEFAULTS.items() if k in name), None)
        if hit is None:
            continue
        versions, note = hit
        stmt = pg_insert(RegionTextbook).values(
            region_code=code, region_name=name, level=1,
            versions=versions, note=note or None, verified=False)
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                index_elements=["region_code"],
                set_={"versions": versions, "note": note or None},
                where=(RegionTextbook.verified.is_(False)))  # 不覆盖已校对的
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["region_code"])
        res = await db.execute(stmt)
        if res.rowcount:
            inserted += 1
        else:
            skipped += 1
    await db.flush()
    return {"provinces": len(provs), "written": inserted, "skipped": skipped}


async def list_map(db: AsyncSession, *, level: int | None = None,
                   skip: int = 0, limit: int = 50) -> dict:
    q = sa.select(RegionTextbook)
    cq = sa.select(sa.func.count()).select_from(RegionTextbook)
    if level is not None:
        q = q.where(RegionTextbook.level == level)
        cq = cq.where(RegionTextbook.level == level)
    total = (await db.execute(cq)).scalar() or 0
    rows = (await db.execute(
        q.order_by(RegionTextbook.level, RegionTextbook.region_code)
        .offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [{
        "region_code": r.region_code, "region_name": r.region_name, "level": r.level,
        "versions": r.versions, "note": r.note, "verified": r.verified,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]}


async def upsert(db: AsyncSession, *, region_code: str, versions: list[str],
                 note: str | None, verified: bool) -> dict:
    reg = (await db.execute(
        sa.select(Region).where(Region.code == region_code))).scalar_one_or_none()
    if reg is None:
        from app.core.exceptions import AppError
        raise AppError(code=400, message=f"地区码 {region_code} 不在 region 表中")
    vers = [v.strip() for v in (versions or []) if v.strip()]
    if not vers:
        from app.core.exceptions import AppError
        raise AppError(code=400, message="至少填一个教材版本")
    await db.execute(pg_insert(RegionTextbook).values(
        region_code=region_code, region_name=reg.name, level=reg.level,
        versions=vers, note=(note or None), verified=verified
    ).on_conflict_do_update(
        index_elements=["region_code"],
        set_={"region_name": reg.name, "level": reg.level, "versions": vers,
              "note": (note or None), "verified": verified, "updated_at": sa.func.now()}))
    await db.flush()
    return {"region_code": region_code}


async def delete(db: AsyncSession, region_code: str) -> dict:
    await db.execute(sa.delete(RegionTextbook).where(
        RegionTextbook.region_code == region_code))
    await db.flush()
    return {"deleted": region_code}


async def textbook_for(db: AsyncSession, region_code: str | None) -> dict | None:
    """给定任意级地区码,逐级上溯(区县6→市4→省2)取最近一条教材映射。"""
    if not region_code:
        return None
    code = str(region_code)
    # 候选码:精确 → 市级(前4) → 省级(前2),按精确优先
    cands = [code]
    if len(code) >= 4:
        cands.append(code[:4])
    if len(code) >= 2:
        cands.append(code[:2])
    rows = (await db.execute(sa.select(RegionTextbook).where(
        RegionTextbook.region_code.in_(cands)))).scalars().all()
    by = {r.region_code: r for r in rows}
    for c in cands:                          # 精确优先,再市,再省
        if c in by:
            r = by[c]
            return {"region_code": r.region_code, "region_name": r.region_name,
                    "versions": r.versions, "note": r.note, "verified": r.verified}
    return None
