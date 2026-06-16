"""优惠券（用户侧，SP-4）：兑换码领取 / 我的券 / 下单可用券。

后台发券/建券在 admin.py；下单抵扣在 orders.py。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.services import coupon_service

router = APIRouter(prefix="/coupons", tags=["coupons"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/mine", response_model=None)
async def my_coupons(db: DbDep, current_user: UserDep,
                     status: str = Query("unused", description="unused|used|all")):
    await get_rls_db(db, str(current_user.id))
    return make_ok(await coupon_service.list_mine(
        db, user_id=current_user.id, status=status))


@router.post("/redeem", response_model=None)
async def redeem_coupon(body: dict, db: DbDep, current_user: UserDep):
    """输入兑换码领券。body={code}。"""
    await get_rls_db(db, str(current_user.id))
    res = await coupon_service.redeem(
        db, user_id=current_user.id, code=(body or {}).get("code", ""))
    await db.commit()
    return make_ok(res)


@router.get("/applicable", response_model=None)
async def applicable_coupons(db: DbDep, current_user: UserDep,
                             amount_fen: int = Query(..., ge=0),
                             scope: str = Query("all")):
    """下单页：对该金额/类型可用的券及抵扣额。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await coupon_service.list_applicable(
        db, user_id=current_user.id, amount_fen=amount_fen, scope=scope))
