"""课程单元「发布闸门」admin API。独立模块,避免与 admin.py 并发改动冲突。

单元默认 draft(整理中,学生不可见);整理好后发布(published)才对学生可见。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import curriculum_service

router = APIRouter(prefix="/admin/curriculum", tags=["admin-curriculum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class UnitStatusIn(BaseModel):
    status: str = Field(..., pattern="^(draft|published)$")


class BulkStatusIn(BaseModel):
    textbook_version: str
    grade: str
    semester: str
    status: str = Field(..., pattern="^(draft|published)$")


@router.put("/units/{unit_id}/status", response_model=BaseResponse[dict])
async def set_unit_status_api(unit_id: uuid.UUID, body: UnitStatusIn, db: DbDep, admin: AdminDep):
    """发布/下架单个单元(draft ↔ published)。"""
    n = await curriculum_service.set_unit_status(db, unit_id=unit_id, status=body.status)
    await db.commit()
    return make_ok({"updated": n, "status": body.status})


@router.post("/units/publish-bulk", response_model=BaseResponse[dict])
async def publish_bulk_api(body: BulkStatusIn, db: DbDep, admin: AdminDep):
    """整学期一键发布/下架(某 教材版+年级+学期 下全部单元)。整理好一次性发布。"""
    n = await curriculum_service.set_units_status_bulk(
        db, textbook_version=body.textbook_version, grade=body.grade,
        semester=body.semester, status=body.status)
    await db.commit()
    return make_ok({"updated": n, "status": body.status})
