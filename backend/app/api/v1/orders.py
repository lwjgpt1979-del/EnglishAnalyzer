"""订单 API（创建 + 查询 + 发起支付）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d2_payments import Order, PaymentConfirmLog
from app.schemas.base import BaseResponse, make_ok
from app.schemas.payments import (
    AppealCreate, OrderCreate, OrderOut, PayParamsOut,
    PaymentConfirmCreate, PaymentConfirmOut, RefundOut,
)
from app.services import (
    order_service, payment_account_service, refund_service, wechat_pay_service,
)
from app.services.auth_service import is_minor_14_to_17

router = APIRouter(prefix="/orders", tags=["orders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/semester-pricing", response_model=BaseResponse[dict])
async def semester_pricing(db: DbDep, current_user: UserDep):
    """学期会员定价（元/学期），运营后台可改；前端购买页据此显示，不写死。"""
    from app.services.pricing_service import get_semester_pricing
    p = await get_semester_pricing(db)
    return make_ok({"basic": p.basic, "pro": p.pro, "promax": p.promax})


@router.get("/tier-pricing", response_model=BaseResponse[dict])
async def tier_pricing(current_user: UserDep):
    """档位会员按份计价（每份 6 个月）。前端购买页据此显示，不写死价格。"""
    return make_ok({
        "unit_months": order_service.UNIT_MONTHS,
        "tiers": [
            {"key": "basic", "name": "基础", "unit_price_fen": order_service.UNIT_PRICE_FEN["basic"]},
            {"key": "pro", "name": "Pro", "unit_price_fen": order_service.UNIT_PRICE_FEN["pro"]},
            {"key": "promax", "name": "ProMax", "unit_price_fen": order_service.UNIT_PRICE_FEN["promax"]},
        ],
    })


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
    if body.addon_feature_key:
        pass   # 加量包：金额由后端按配置取，无需额外校验
    elif body.semesters:
        if not body.semesters:
            raise AppError(code=400, message="V2 模式 semesters 不能为空列表")
    elif body.quantity is not None:
        # 按份：每份 6 个月
        if body.quantity < 1 or body.quantity > 24:
            raise AppError(code=400, message="份数需在 1-24 之间")
    else:
        # 遗留按月：校验 duration_months
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
        quantity=body.quantity,
        order_type=body.order_type,
        semesters=body.semesters,
        addon_feature_key=body.addon_feature_key,
        is_promotional=body.is_promotional,
        payment_confirm_log_id=body.payment_confirm_log_id,
    )
    # 固化收款主体 + 结算分公司（按受益人城市路由；退款按此原路退回）
    beneficiary = current_user if beneficiary_id == current_user.id \
        else await db.get(User, beneficiary_id)
    acc = await payment_account_service.resolve_for_order(db, beneficiary)
    if acc is not None:
        order.payment_account_id = acc.id
    branch_id = await payment_account_service.branch_company_id_for(db, beneficiary)
    if branch_id is not None:
        order.branch_company_id = branch_id

    # 优惠券抵扣（SP-4）：按订单类型推导 scope 后校验+核销
    if body.coupon_grant_id:
        from app.services import coupon_service
        scope = ("addon" if body.addon_feature_key
                 else "semester" if body.semesters
                 else body.order_type)
        await coupon_service.apply_to_order(
            db, grant_id=body.coupon_grant_id, user_id=current_user.id,
            order=order, scope=scope)

    # 反写支付确认记录的 order_id（举证关联，§4.6.3）
    if body.payment_confirm_log_id:
        log = await db.get(PaymentConfirmLog, body.payment_confirm_log_id)
        if log and log.user_id == current_user.id and log.order_id is None:
            log.order_id = order.id
    await db.commit()
    await db.refresh(order)
    return make_ok(OrderOut.model_validate(order))


@router.post("/payment-confirm", response_model=BaseResponse[PaymentConfirmOut])
async def payment_confirm(
    body: PaymentConfirmCreate, request: Request, db: DbDep, current_user: UserDep,
):
    """支付前合规确认留存（§4.6.3）。两个勾选缺一不可；服务端补 IP/UA/时间戳。

    客户端须在此接口成功（拿到 log_id）后，再携 log_id 下单+发起支付；
    本接口失败则客户端不得放行支付。
    """
    if not (body.checkbox_refund_policy and body.checkbox_digital_service):
        raise AppError(code=400, message="请先阅读并勾选退款规则与虚拟服务说明")
    await get_rls_db(db, str(current_user.id))
    ip = (request.headers.get("x-real-ip")
          or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
          or (request.client.host if request.client else None))
    log = PaymentConfirmLog(
        id=uuid.uuid4(),
        user_id=current_user.id,
        ip_address=ip,
        device_id=body.device_id,
        session_id=body.session_id,
        user_agent=request.headers.get("user-agent"),
        checkbox_refund_policy=body.checkbox_refund_policy,
        checkbox_digital_service=body.checkbox_digital_service,
        plan_snapshot=body.plan_snapshot,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return make_ok(PaymentConfirmOut(log_id=log.id))


@router.get("/", response_model=BaseResponse[list[OrderOut]])
async def list_my_orders(db: DbDep, current_user: UserDep):
    """当前用户订单列表（受益人视角，含退款/申诉状态），供订单记录页。"""
    await get_rls_db(db, str(current_user.id))
    rows = await db.execute(
        select(Order)
        .where(Order.beneficiary_id == current_user.id)
        .order_by(Order.created_at.desc())
    )
    orders = rows.scalars().all()
    return make_ok([OrderOut.model_validate(o) for o in orders])


@router.post("/{order_id}/refund", response_model=BaseResponse[RefundOut])
async def request_refund(order_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """发起退款（§4.5，7天内规则引擎自动判定；已使用转人工）。"""
    await get_rls_db(db, str(current_user.id))
    rec = await refund_service.request_refund(db, current_user, order_id)
    await db.commit()
    await db.refresh(rec)
    return make_ok(RefundOut.model_validate(rec))


@router.post("/{order_id}/appeal", response_model=BaseResponse[RefundOut])
async def submit_appeal(
    order_id: uuid.UUID, body: AppealCreate, db: DbDep, current_user: UserDep,
):
    """超7天有理由申诉（§4.5，4 类；重复购买可自动退）。"""
    await get_rls_db(db, str(current_user.id))
    rec = await refund_service.submit_appeal(
        db, current_user, order_id,
        appeal_type=body.appeal_type, note=body.note,
        evidence_urls=body.evidence_urls,
    )
    await db.commit()
    await db.refresh(rec)
    return make_ok(RefundOut.model_validate(rec))


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

    # 按订单固化的收款主体 + 渠道适配器生成支付参数
    from app.services.payment.base import get_provider
    creds = await payment_account_service.resolve_creds_for_order(db, order)
    provider = get_provider(creds.provider)
    params = await provider.create_payment(order, creds, openid=current_user.openid)
    return make_ok(PayParamsOut(**params))
