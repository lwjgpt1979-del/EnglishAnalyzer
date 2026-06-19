"""行政区划地区 API(公开参考数据,免鉴权)。

懒加载:不传 parent 返回省;传 parent 返回其下级(市/区县/乡镇)。所有前端(admin/学生/机构)共用,
不再各自硬编码 cities。code 与 user.city_code 同源。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.d21_region import Region
from app.schemas.base import BaseResponse, make_ok

router = APIRouter(prefix="/regions", tags=["regions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=BaseResponse[list[dict]])
async def list_regions(db: DbDep, parent: str | None = Query(None, description="上级 code;空=省级")):
    """懒加载地区:无 parent → 省;有 parent → 其直接下级,按 code 升序。"""
    stmt = select(Region).order_by(Region.code)
    stmt = stmt.where(Region.parent_code.is_(None)) if not parent else stmt.where(Region.parent_code == parent)
    rows = (await db.execute(stmt)).scalars().all()
    # 哪些子节点自身还有下级 → 非叶(供级联懒加载判断是否可展开)
    codes = [r.code for r in rows]
    have_kids: set[str] = set()
    if codes:
        have_kids = set((await db.execute(
            select(Region.parent_code).where(Region.parent_code.in_(codes)).distinct()
        )).scalars().all())
    return make_ok([
        {"code": r.code, "name": r.name, "parent_code": r.parent_code,
         "level": r.level, "leaf": r.code not in have_kids}
        for r in rows
    ])
