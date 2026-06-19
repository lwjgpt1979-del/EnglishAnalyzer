"""行政区划地区 API(公开参考数据,免鉴权)。

懒加载:不传 parent 返回省;传 parent 返回其下级(市/区县/乡镇)。所有前端(admin/学生/机构)共用,
不再各自硬编码 cities。code 与 user.city_code 同源。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import BaseResponse, make_ok
from app.services import region_service

router = APIRouter(prefix="/regions", tags=["regions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=BaseResponse[list[dict]])
async def list_regions(db: DbDep, parent: str | None = Query(None, description="上级 code;空=省级")):
    """懒加载地区:无 parent → 省;有 parent → 其直接下级。所有前端共用,免鉴权。"""
    return make_ok(await region_service.list_children(db, parent))
