"""机构学生采购 service（D-122）：下单 + 生成激活码 + 采购记录。"""
from __future__ import annotations

import random
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import ActivationCode, InstitutionPurchase

_CODE_CHARS = string.ascii_uppercase + string.digits
_TIER_MONTHLY_FEN = {"basic": 1500, "pro": 3000, "promax": 5000}


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = "".join(random.choices(_CODE_CHARS, k=12))
        r = await db.execute(select(ActivationCode).where(ActivationCode.code == code))
        if r.scalar_one_or_none() is None:
            return code
    raise AppError(code=500, message="激活码生成失败，请重试")


async def create_purchase(
    db: AsyncSession, *, institution_id: uuid.UUID, created_by: uuid.UUID,
    tier: str, duration_months: int, quantity: int,
) -> tuple[InstitutionPurchase, list[ActivationCode]]:
    if tier not in _TIER_MONTHLY_FEN:
        raise AppError(code=400, message="档位无效")
    if duration_months < 1 or quantity < 1:
        raise AppError(code=400, message="时长/数量必须 ≥ 1")

    amount_fen = _TIER_MONTHLY_FEN[tier] * duration_months * quantity
    purchase = InstitutionPurchase(
        id=uuid.uuid4(), institution_id=institution_id, tier=tier,  # type: ignore[arg-type]
        duration_months=duration_months, quantity=quantity,
        amount_fen=amount_fen, status="paid", created_by=created_by,
    )
    db.add(purchase)
    await db.flush()

    codes: list[ActivationCode] = []
    for _ in range(quantity):
        c = ActivationCode(
            id=uuid.uuid4(), code=await _unique_code(db), purchase_id=purchase.id,
            tier=tier, duration_months=duration_months, status="unused",  # type: ignore[arg-type]
        )
        db.add(c)
        codes.append(c)
    await db.flush()
    return purchase, codes


async def list_purchases(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> list[tuple[InstitutionPurchase, int, int]]:
    purchases = (await db.execute(
        select(InstitutionPurchase)
        .where(InstitutionPurchase.institution_id == institution_id)
        .order_by(InstitutionPurchase.created_at.desc())
    )).scalars().all()
    out: list[tuple[InstitutionPurchase, int, int]] = []
    for p in purchases:
        total = (await db.execute(
            select(func.count()).select_from(ActivationCode)
            .where(ActivationCode.purchase_id == p.id)
        )).scalar_one()
        used = (await db.execute(
            select(func.count()).select_from(ActivationCode)
            .where(ActivationCode.purchase_id == p.id, ActivationCode.status == "used")
        )).scalar_one()
        out.append((p, used, total))
    return out


async def get_purchase_codes(
    db: AsyncSession, *, institution_id: uuid.UUID, purchase_id: uuid.UUID
) -> list[ActivationCode]:
    p = (await db.execute(
        select(InstitutionPurchase).where(
            InstitutionPurchase.id == purchase_id,
            InstitutionPurchase.institution_id == institution_id,
        )
    )).scalar_one_or_none()
    if p is None:
        raise AppError(code=404, message="采购单不存在或不属于本机构")
    codes = (await db.execute(
        select(ActivationCode).where(ActivationCode.purchase_id == purchase_id)
        .order_by(ActivationCode.created_at.asc())
    )).scalars().all()
    return list(codes)
