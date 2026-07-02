"""行政区划地区 service:懒加载读 + 后台维护(增删改)。region 表为唯一数据源。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d21_region import Region


def _bare(s: str) -> str:
    import re
    return re.sub(r"(省|市|自治区|特别行政区|壮族|回族|维吾尔|自治州|地区)", "", s or "")


def _hit(r: Region, name: str) -> bool:
    return r.name in name or (len(_bare(r.name)) >= 2 and _bare(r.name) in name)


async def _match_child(db: AsyncSession, parent_code: str | None, name: str) -> Region | None:
    """在 parent 的直接下级里找名字命中文本的那个(整体名或去后缀名出现在 name 中)。"""
    q = (select(Region).where(Region.parent_code.is_(None)) if parent_code is None
         else select(Region).where(Region.parent_code == parent_code))
    children = (await db.execute(q)).scalars().all()
    return next((c for c in children if _hit(c, name)), None)


async def region_from_name(
    db: AsyncSession, name: str, *, max_level: int = 2,
) -> tuple[str | None, str | None]:
    """从文本匹配行政区划,返回 (最细级 code, 逐级拼接名)。匹配不到 → (None, None)。

    默认 max_level=2(省→市)保持历史行为(市级码与 user.city_code 同源)。
    需要区县/乡镇时传 max_level=3/4:在**已定位的上级下**逐级下钻(限定子级内匹配,
    避免乡镇重名的全国歧义)——只有上级链完整出现在文本里才会钻到更细级。
    """
    if not name:
        return None, None
    chain: list[Region] = []
    node = await _match_child(db, None, name)          # 省
    if node is None:
        # 名字里没省 → 按市级(level=2)全国匹配,回推所属省,作为下钻起点
        city = next((c for c in (await db.execute(
            select(Region).where(Region.level == 2))).scalars().all()
            if len(_bare(c.name)) >= 2 and _bare(c.name) in name), None)
        if city is None:
            return None, None
        prov = (await db.execute(
            select(Region).where(Region.code == city.parent_code))).scalar_one_or_none()
        if prov is not None:
            chain.append(prov)
        node = city
    chain.append(node)
    while node.level < max_level:                       # 逐级下钻(市→区县→乡镇)
        child = await _match_child(db, node.code, name)
        if child is None:
            break
        chain.append(child)
        node = child
    return chain[-1].code, "".join(r.name for r in chain)


async def list_children(db: AsyncSession, parent_code: str | None) -> list[dict]:
    """懒加载:无 parent → 省;有 parent → 直接下级。附 leaf(是否还有下级)。"""
    stmt = select(Region).order_by(Region.code)
    stmt = stmt.where(Region.parent_code.is_(None)) if not parent_code else stmt.where(Region.parent_code == parent_code)
    rows = (await db.execute(stmt)).scalars().all()
    codes = [r.code for r in rows]
    have_kids: set[str] = set()
    if codes:
        have_kids = set((await db.execute(
            select(Region.parent_code).where(Region.parent_code.in_(codes)).distinct()
        )).scalars().all())
    return [{"code": r.code, "name": r.name, "parent_code": r.parent_code,
             "level": r.level, "leaf": r.code not in have_kids} for r in rows]


async def create_region(db: AsyncSession, *, code: str, name: str,
                        parent_code: str | None, level: int) -> Region:
    if (await db.get(Region, code)) is not None:
        raise AppError(code=409, message=f"区划代码 {code} 已存在")
    if parent_code and (await db.get(Region, parent_code)) is None:
        raise AppError(code=400, message=f"上级 {parent_code} 不存在")
    r = Region(code=code, name=name, parent_code=parent_code or None, level=level)
    db.add(r)
    await db.flush()
    return r


async def update_region(db: AsyncSession, *, code: str, name: str) -> Region:
    r = await db.get(Region, code)
    if r is None:
        raise AppError(code=404, message="地区不存在")
    r.name = name
    await db.flush()
    return r


async def delete_region(db: AsyncSession, *, code: str) -> None:
    r = await db.get(Region, code)
    if r is None:
        raise AppError(code=404, message="地区不存在")
    has_kids = (await db.execute(
        select(Region.code).where(Region.parent_code == code).limit(1))).first() is not None
    if has_kids:
        raise AppError(code=409, message="该地区下有下级,请先删除下级")
    await db.delete(r)
    await db.flush()
