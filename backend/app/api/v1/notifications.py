"""站内消息中心 API（Module 7B / D-074）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.notifications import (
    NotificationOut,
    NotificationListOut,
    UnreadCountOut,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/", response_model=BaseResponse[NotificationListOut])
async def list_notifications_api(
    db: DbDep,
    current_user: UserDep,
    channel: str | None = Query(None),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    await get_rls_db(db, str(current_user.id))
    items, total, unread = await notification_service.list_notifications(
        db, user_id=current_user.id, channel=channel,
        unread_only=unread_only, skip=skip, limit=limit,
    )
    return make_ok(NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    ))


@router.get("/unread-count", response_model=BaseResponse[UnreadCountOut])
async def unread_count_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    c = await notification_service.unread_count(db, user_id=current_user.id)
    return make_ok(UnreadCountOut(count=c))


@router.patch("/{notif_id}/read", response_model=BaseResponse[NotificationOut])
async def mark_read_api(notif_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.mark_read(db, user_id=current_user.id, notif_id=notif_id)
    await db.commit()
    return make_ok(NotificationOut.model_validate(n))


@router.post("/read-all", response_model=BaseResponse[dict])
async def mark_all_read_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.mark_all_read(db, user_id=current_user.id)
    await db.commit()
    return make_ok({"affected": n})


@router.delete("/read", response_model=BaseResponse[dict])
async def delete_read_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.delete_read(db, user_id=current_user.id)
    await db.commit()
    return make_ok({"deleted": n})
