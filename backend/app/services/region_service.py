"""行政区划地区 service:懒加载读 + 后台维护(增删改)。region 表为唯一数据源。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d21_region import Region


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
