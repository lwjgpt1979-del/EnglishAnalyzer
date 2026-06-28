"""机构学生采购 service 测试（D-122）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, User
from app.services import institution_purchase_service as svc


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst_admin(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    admin = uuid.uuid4()
    s.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await s.flush()
    return inst.id, admin


@pytest.mark.asyncio
async def test_create_purchase_generates_codes(db_session):
    inst_id, admin = await _inst_admin(db_session)
    purchase, codes = await svc.create_purchase(
        db_session, institution_id=inst_id, created_by=admin,
        tier="pro", duration_months=12, quantity=3)
    assert purchase.amount_fen == 3000 * 12 * 3
    assert purchase.status == "paid"
    assert len(codes) == 3
    assert all(len(c.code) == 12 for c in codes)


@pytest.mark.asyncio
async def test_get_purchase_codes_cross_institution_404(db_session):
    a_id, a_admin = await _inst_admin(db_session, "A")
    b_id, b_admin = await _inst_admin(db_session, "B")
    purchase, _ = await svc.create_purchase(
        db_session, institution_id=b_id, created_by=b_admin,
        tier="basic", duration_months=1, quantity=1)
    with pytest.raises(AppError):
        await svc.get_purchase_codes(db_session, institution_id=a_id, purchase_id=purchase.id)


@pytest.mark.asyncio
async def test_create_purchase_reads_backend_pricing(db_session):
    """计费读后台配置：改 institution_code_pricing 后金额随之变化（显示价=实扣价）。"""
    from app.schemas.institution import InstitutionCodePricing
    from app.services import pricing_service

    inst_id, admin = await _inst_admin(db_session)
    # 运营把 pro 改成 8888 分/月
    await pricing_service.update_institution_code_pricing(
        db_session, pricing=InstitutionCodePricing(basic=1000, pro=8888, promax=9999),
        updated_by=admin)
    purchase, _ = await svc.create_purchase(
        db_session, institution_id=inst_id, created_by=admin,
        tier="pro", duration_months=2, quantity=4)
    assert purchase.amount_fen == 8888 * 2 * 4


@pytest.mark.asyncio
async def test_list_purchases(db_session):
    inst_id, admin = await _inst_admin(db_session)
    await svc.create_purchase(db_session, institution_id=inst_id, created_by=admin,
                              tier="basic", duration_months=1, quantity=2)
    rows = await svc.list_purchases(db_session, institution_id=inst_id)
    assert len(rows) == 1
    _, used, total = rows[0]
    assert used == 0 and total == 2
