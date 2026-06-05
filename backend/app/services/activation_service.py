"""激活码兑换 service（D-122）：学生输码 → 发会员 + 归属机构。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Student
from app.models.d2_payments import ActivationCode, InstitutionPurchase, Order
from app.services import membership_service


async def activate_code(
    db: AsyncSession, *, student_user_id: uuid.UUID, code: str
):
    now = datetime.now(timezone.utc)
    ac = (await db.execute(
        select(ActivationCode).where(
            ActivationCode.code == code, ActivationCode.status == "unused"
        )
    )).scalar_one_or_none()
    if ac is None:
        raise AppError(code=400, message="激活码无效或已使用")

    purchase = await db.get(InstitutionPurchase, ac.purchase_id)
    if purchase is None:
        raise AppError(code=400, message="激活码对应采购单不存在")

    # 普通微信学生 role=student 但可能尚无 students 行（plain wx 登录只建 User）。
    # 激活时若缺则补建，使正常学生也能激活（D-129 测试发现）。
    student = await db.get(Student, student_user_id)
    if student is None:
        student = Student(id=student_user_id)
        db.add(student)
        await db.flush()
    if student.institution_id is not None:
        raise AppError(code=409, message="您已是机构学生，不能重复激活")

    # 造一张已支付合成 Order（机构采购激活，不走真实支付）
    order = Order(
        id=uuid.uuid4(),
        order_no=f"ACT{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
        payer_id=purchase.created_by,
        beneficiary_id=student_user_id,
        order_type="new",  # type: ignore[arg-type]
        tier=ac.tier,
        duration_months=ac.duration_months,
        amount_fen=0,
        status="paid",  # type: ignore[arg-type]
    )
    db.add(order)
    await db.flush()

    membership = await membership_service.activate_membership(db, order=order)

    student.institution_id = purchase.institution_id
    ac.status = "used"
    ac.used_by = student_user_id
    ac.used_at = now
    await db.flush()
    return membership
