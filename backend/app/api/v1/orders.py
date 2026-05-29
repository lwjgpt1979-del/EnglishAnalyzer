"""订单 API（创建 + 查询 + 发起支付）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.payments import OrderCreate, OrderOut, PayParamsOut
from app.services import order_service, wechat_pay_service
from app.services.auth_service import is_minor_14_to_17

router = APIRouter(prefix="/orders", tags=["orders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/", response_model=BaseResponse[OrderOut])
async def create_order(body: OrderCreate, db: DbDep, current_user: UserDep):
    """创建待支付订单。支持自付（payer = beneficiary = 当前用户）和亲人代付。

    档位只能是 basic/pro/promax；时长只能是 1/3/12 个月。
    代付时 target_student_id 须为已绑定学生；14-17 岁学生由亲人代付视为已获监护人同意（§4.1 / D-073）。
    """
    await get_rls_db(db, str(current_user.id))

    # 解析 beneficiary_id
    beneficiary_id = body.target_student_id or current_user.id

    if body.target_student_id and body.target_student_id != current_user.id:
        # 代付：必须是绑定的亲人
        from app.services import relative_service
        await relative_service.assert_bound(
            db, relative_id=current_user.id, student_id=body.target_student_id,
        )
        # 14-17 岁学生由亲人代付视为已获监护人同意（§4.1 / D-073）
        from sqlalchemy import select as _sel
        from app.models.d1_users import User as _U
        bu_r = await db.execute(_sel(_U).where(_U.id == body.target_student_id))
        beneficiary = bu_r.scalar_one_or_none()
        if beneficiary and beneficiary.birth_year:
            age = datetime.now(timezone.utc).year - beneficiary.birth_year
            if 14 <= age <= 17 and beneficiary.minor_purchase_consent_at is None:
                beneficiary.minor_purchase_consent_at = datetime.now(timezone.utc)
    else:
        # 本人购买：14-17 岁首次购买须勾选监护人同意
        if is_minor_14_to_17(current_user) and current_user.minor_purchase_consent_at is None:
            if not body.minor_consent:
                raise AppError(code=400, message="14-17岁用户首次购买请勾选「已告知监护人并获得同意」")
            current_user.minor_purchase_consent_at = datetime.now(timezone.utc)

    if body.tier not in order_service.ALLOWED_TIERS:
        raise AppError(
            code=400, message=f"无效档位：{body.tier}，可选：basic/pro/promax"
        )
    if body.duration_months not in order_service.ALLOWED_DURATIONS:
        raise AppError(
            code=400, message=f"无效时长：{body.duration_months}，可选：1/3/12"
        )
    if body.order_type not in order_service.ALLOWED_ORDER_TYPES:
        raise AppError(code=400, message=f"无效订单类型：{body.order_type}")

    order = await order_service.create_order(
        db,
        payer_id=current_user.id,
        beneficiary_id=beneficiary_id,
        tier=body.tier,
        duration_months=body.duration_months,
        order_type=body.order_type,
    )
    await db.commit()
    await db.refresh(order)
    return make_ok(OrderOut.model_validate(order))


@router.get("/{order_id}", response_model=BaseResponse[OrderOut])
async def get_order(order_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """查询订单详情（付款人或受益人可见）。"""
    await get_rls_db(db, str(current_user.id))
    order = await order_service.get_order(
        db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise AppError(code=404, message="订单不存在")
    return make_ok(OrderOut.model_validate(order))


@router.post("/{order_id}/pay", response_model=BaseResponse[PayParamsOut])
async def pay_order(order_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """发起微信支付，返回 wx.requestPayment() 所需参数。

    订单必须处于 pending 状态；微信 API 调用失败时返回 2003。
    """
    await get_rls_db(db, str(current_user.id))
    order = await order_service.get_order(
        db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise AppError(code=404, message="订单不存在")
    if order.status != "pending":
        raise AppError(
            code=400, message=f"订单状态为 {order.status}，无法发起支付"
        )

    prepay_id = await wechat_pay_service.get_prepay_id(order, current_user.openid)
    params = wechat_pay_service.build_pay_params(prepay_id)
    return make_ok(PayParamsOut(**params))
