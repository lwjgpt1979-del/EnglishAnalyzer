"""发票申请 API（用户侧，§5.4）。后台开具/驳回在 admin.py。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/mine", response_model=None)
async def my_invoices(db: DbDep, current_user: UserDep):
    """我的开票申请列表。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await invoice_service.list_mine(db, user_id=current_user.id))


@router.post("", response_model=None)
async def request_invoice(body: dict, db: DbDep, current_user: UserDep):
    """对已支付订单申请开票。body={order_id, title_type, title, tax_no?, content?, email?}。"""
    await get_rls_db(db, str(current_user.id))
    rec = await invoice_service.request_invoice(
        db, user_id=current_user.id, order_id=uuid.UUID(body["order_id"]),
        title_type=(body.get("title_type") or "personal"), title=body.get("title", ""),
        tax_no=body.get("tax_no"), content=body.get("content"), email=body.get("email"))
    await db.commit()
    return make_ok({"id": str(rec.id), "status": rec.status})
