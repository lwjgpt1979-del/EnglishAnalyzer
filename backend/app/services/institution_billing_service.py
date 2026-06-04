"""机构账单 service（D-125）：采购 + 续费 合并账单。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d2_payments import InstitutionPurchase, Order


async def list_bills(db: AsyncSession, *, institution_id: uuid.UUID) -> list[dict]:
    bills: list[dict] = []

    purchases = (await db.execute(
        select(InstitutionPurchase)
        .where(InstitutionPurchase.institution_id == institution_id)
    )).scalars().all()
    for p in purchases:
        bills.append({
            "date": p.created_at,
            "type": "采购",
            "summary": f"{p.tier} × {p.quantity}（{p.duration_months}月）",
            "amount_fen": p.amount_fen,
        })

    admin_ids = select(User.id).where(User.institution_id == institution_id)
    renews = (await db.execute(
        select(Order)
        .where(Order.order_type == "renew", Order.payer_id.in_(admin_ids))
    )).scalars().all()
    for o in renews:
        bills.append({
            "date": o.created_at,
            "type": "续费",
            "summary": f"{o.tier} 续费 {o.duration_months}月",
            "amount_fen": o.amount_fen,
        })

    bills.sort(key=lambda b: b["date"], reverse=True)
    return bills
