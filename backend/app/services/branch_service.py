"""分公司管理 + 城市归属（阶段③：地方子公司按城市分收业务）。

bank_account 用字段加密存库（core/crypto），列表不回明文，只返回"是否已配置"。
城市归属：同一时刻一个城市只能归一家分公司（DB 部分唯一索引保证）。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.exceptions import AppError
from app.models.d10_branch import BranchCompany, BranchCompanyCity, PaymentAccount


def _to_item(b: BranchCompany, cities: list[BranchCompanyCity],
             linked: list[PaymentAccount]) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "contact_phone": b.contact_phone,
        "manager_user_id": b.manager_user_id,
        "commission_rate": float(b.commission_rate) if b.commission_rate is not None else None,
        "legal_name": b.legal_name,
        "tax_number": b.tax_number,
        "bank_name": b.bank_name,
        "bank_account_set": bool(b.bank_account),     # 不回明文
        "is_active": b.is_active,
        "cities": [
            {"id": c.id, "city_code": c.city_code,
             "effective_from": c.effective_from.isoformat() if c.effective_from else None,
             "effective_to": c.effective_to.isoformat() if c.effective_to else None}
            for c in cities
        ],
        "payment_accounts": [
            {"id": a.id, "name": a.name, "provider": a.provider} for a in linked
        ],
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


async def list_branches(db: AsyncSession) -> list[dict]:
    branches = (await db.execute(
        select(BranchCompany).order_by(BranchCompany.created_at.asc())
    )).scalars().all()
    out = []
    for b in branches:
        cities = (await db.execute(
            select(BranchCompanyCity).where(BranchCompanyCity.branch_company_id == b.id)
            .order_by(BranchCompanyCity.created_at.asc())
        )).scalars().all()
        linked = (await db.execute(
            select(PaymentAccount).where(PaymentAccount.branch_company_id == b.id)
        )).scalars().all()
        out.append(_to_item(b, cities, linked))
    return out


async def create_branch(db: AsyncSession, *, name: str, contact_phone: str | None = None,
                        commission_rate: float | None = None, legal_name: str | None = None,
                        tax_number: str | None = None, bank_name: str | None = None,
                        bank_account: str | None = None) -> BranchCompany:
    b = BranchCompany(
        id=uuid.uuid4(), name=name, contact_phone=contact_phone,
        commission_rate=commission_rate, legal_name=legal_name,
        tax_number=tax_number, bank_name=bank_name,
        bank_account=crypto.encrypt(bank_account) if bank_account else None,
        is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


async def update_branch(db: AsyncSession, branch_id: uuid.UUID, *, fields: dict) -> BranchCompany:
    b = await db.get(BranchCompany, branch_id)
    if b is None:
        raise AppError(code=404, message="分公司不存在")
    plain = {"name", "contact_phone", "commission_rate", "legal_name",
             "tax_number", "bank_name"}
    for k, v in fields.items():
        if k in plain and v is not None:
            setattr(b, k, v)
    # 银行账户：非空则加密更新（空字符串表示清空）
    if "bank_account" in fields and fields["bank_account"] is not None:
        ba = fields["bank_account"]
        b.bank_account = crypto.encrypt(ba) if ba else None
    await db.flush()
    return b


async def toggle_active(db: AsyncSession, branch_id: uuid.UUID) -> BranchCompany:
    b = await db.get(BranchCompany, branch_id)
    if b is None:
        raise AppError(code=404, message="分公司不存在")
    b.is_active = not b.is_active
    await db.flush()
    return b


async def add_city(db: AsyncSession, branch_id: uuid.UUID, *, city_code: str,
                   effective_from: dt.date | None = None) -> BranchCompanyCity:
    b = await db.get(BranchCompany, branch_id)
    if b is None:
        raise AppError(code=404, message="分公司不存在")
    # 同一城市当前只能归属一家分公司
    existing = await db.scalar(
        select(BranchCompanyCity).where(and_(
            BranchCompanyCity.city_code == city_code,
            BranchCompanyCity.effective_to.is_(None),
        ))
    )
    if existing is not None:
        raise AppError(code=400, message=f"城市 {city_code} 当前已归属其他分公司，请先解除")
    c = BranchCompanyCity(
        id=uuid.uuid4(), branch_company_id=branch_id, city_code=city_code,
        effective_from=effective_from or dt.date.today(),
    )
    db.add(c)
    await db.flush()
    return c


async def remove_city(db: AsyncSession, city_id: uuid.UUID) -> None:
    """解除城市归属：置 effective_to=今天（保留历史，不物理删，结算可追溯）。"""
    c = await db.get(BranchCompanyCity, city_id)
    if c is None:
        raise AppError(code=404, message="城市归属记录不存在")
    if c.effective_to is None:
        c.effective_to = dt.date.today()
    await db.flush()
