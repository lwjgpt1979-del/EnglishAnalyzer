"""机构入驻审核 service（D-123，超管侧）。"""
from __future__ import annotations

import random
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution
from app.services import admin_auth_service

_PW_CHARS = string.ascii_letters + string.digits


async def create_institution(
    db: AsyncSession, *, name: str, contact_phone: str,
    province_code: str, city_code: str, address: str,
) -> Institution:
    inst = Institution(
        id=uuid.uuid4(), name=name, contact_phone=contact_phone,
        province_code=province_code, city_code=city_code, address=address,
        source="admin",
    )
    db.add(inst)
    await db.flush()
    return inst


async def list_institutions(
    db: AsyncSession, *, status: str | None = None, source: str | None = None
) -> list[Institution]:
    q = select(Institution)
    if status:
        q = q.where(Institution.status == status)
    if source:
        q = q.where(Institution.source == source)
    q = q.order_by(Institution.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def _get(db: AsyncSession, institution_id: uuid.UUID) -> Institution:
    inst = (await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )).scalar_one_or_none()
    if inst is None:
        raise AppError(code=404, message="机构不存在")
    return inst


async def approve_institution(
    db: AsyncSession, *, institution_id: uuid.UUID, admin_username: str
) -> tuple[Institution, str, str]:
    inst = await _get(db, institution_id)
    if str(inst.status) != "pending":
        raise AppError(code=400, message="仅待审核(pending)机构可通过")
    inst.status = "active"  # type: ignore[assignment]
    password = "".join(random.choices(_PW_CHARS, k=10))
    await admin_auth_service.create_institution_admin(
        db, username=admin_username, password=password, institution_id=inst.id)
    await db.flush()
    return inst, admin_username, password


async def reject_institution(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> Institution:
    inst = await _get(db, institution_id)
    inst.status = "suspended"  # type: ignore[assignment]
    await db.flush()
    return inst
