"""教材主数据(curriculum_catalog)admin API——版本/年级/学期 维护 + 上下架。

全站版本/年级/学期可选项与学生内容可见性,均以本表为准(见 CLAUDE.md「主数据上架/下架」铁律)。
上架粒度=版本+年级+学期;可先建版本(内容后补)。独立模块,避免与 admin.py 并发改动冲突。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import curriculum_catalog_service as cat

router = APIRouter(prefix="/admin/curriculum", tags=["admin-curriculum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class CatalogStatusIn(BaseModel):
    status: str = Field(..., pattern="^(draft|published)$")


class CatalogAddIn(BaseModel):
    textbook_version: str = Field(..., min_length=1)
    grade: str = Field(..., min_length=1)
    semester: str = Field(..., min_length=1)


@router.get("/catalog", response_model=BaseResponse[dict])
async def list_catalog_api(
    db: DbDep, admin: AdminDep,
    textbook_version: str | None = None, grade: str | None = None, semester: str | None = None,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
):
    """教材目录分页列表(admin 全见:上架+下架)。"""
    out = await cat.list_catalog(
        db, include_unpublished=True, textbook_version=textbook_version,
        grade=grade, semester=semester, skip=skip, limit=limit)
    return make_ok(out)


@router.get("/catalog/options", response_model=BaseResponse[dict])
async def catalog_options_api(db: DbDep, admin: AdminDep):
    """新增目录表单的候选建议:已存在的版本/年级/学期 + 规范建议(可选可自定义新增)。"""
    from app.services import curriculum_service as cs
    existing = await cat.preference_options(db, include_unpublished=True)
    return make_ok({
        "textbook_versions": sorted(set([*existing["textbook_versions"], *cs.CANONICAL_TEXTBOOKS])),
        "grades": sorted(set([*existing["grades"], *cs.CANONICAL_GRADES]), key=cat._grade_rank),
        "semesters": sorted(set([*existing["semesters"], *cs.CANONICAL_SEMESTERS])),
    })


@router.post("/catalog", response_model=BaseResponse[dict])
async def add_catalog_api(body: CatalogAddIn, db: DbDep, admin: AdminDep):
    """新增一条目录(版本+年级+学期),默认下架;已存在则幂等返回。版本/年级/学期均可自定义。"""
    try:
        row = await cat.add_offering(db, textbook_version=body.textbook_version,
                                     grade=body.grade, semester=body.semester)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return make_ok(row)


@router.put("/catalog/{catalog_id}/status", response_model=BaseResponse[dict])
async def set_catalog_status_api(catalog_id: uuid.UUID, body: CatalogStatusIn, db: DbDep, admin: AdminDep):
    """上架/下架一条目录(published ↔ draft)。"""
    n = await cat.set_status(db, catalog_id=catalog_id, status=body.status)
    return make_ok({"updated": n, "status": body.status})


@router.delete("/catalog/{catalog_id}", response_model=BaseResponse[dict])
async def delete_catalog_api(catalog_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """删除一条目录(仅移除可选项/可见闸门,不删已上传的教材单元内容)。"""
    n = await cat.delete_offering(db, catalog_id=catalog_id)
    return make_ok({"deleted": n})
