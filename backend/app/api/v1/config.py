"""公开配置 API（M11）：小程序启动无需登录即可读取上线主题。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import make_ok
from app.services import theme_service, branding_service

router = APIRouter(prefix="/config", tags=["config"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/theme")
async def get_active_theme(db: DbDep):
    """返回当前上线主题（key + name + tokens），供小程序启动应用。公开无需鉴权。"""
    return make_ok(await theme_service.get_active_theme(db))


@router.get("/branding")
async def get_branding(db: DbDep):
    """返回项目品牌（项目名/slogan），各前端启动读取。公开无需鉴权。"""
    return make_ok(await branding_service.get_branding(db))
