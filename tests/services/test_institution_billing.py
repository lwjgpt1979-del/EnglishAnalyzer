"""机构账单 service 测试（D-125）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import institution_billing_service as svc
from app.services import institution_purchase_service, institution_renew_service


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


async def _student_member(s, inst_id, *, tier="pro"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
                     expires_at=now + dt.timedelta(days=10), is_active=True))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_list_bills_merges_purchase_and_renew(db_session):
    inst_id, admin = await _inst_admin(db_session)
    await institution_purchase_service.create_purchase(
        db_session, institution_id=inst_id, created_by=admin,
        tier="pro", duration_months=6, quantity=2)
    sid = await _student_member(db_session, inst_id, tier="pro")
    await institution_renew_service.batch_renew(
        db_session, institution_id=inst_id, student_ids=[sid],
        duration_months=3, operator_id=admin)

    bills = await svc.list_bills(db_session, institution_id=inst_id)
    types = [b["type"] for b in bills]
    assert "采购" in types and "续费" in types
    dates = [b["date"] for b in bills]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_list_bills_isolated(db_session):
    a_id, a_admin = await _inst_admin(db_session, "A")
    b_id, b_admin = await _inst_admin(db_session, "B")
    await institution_purchase_service.create_purchase(
        db_session, institution_id=b_id, created_by=b_admin,
        tier="basic", duration_months=1, quantity=1)
    sid = await _student_member(db_session, b_id, tier="basic")
    await institution_renew_service.batch_renew(
        db_session, institution_id=b_id, student_ids=[sid],
        duration_months=1, operator_id=b_admin)

    bills_a = await svc.list_bills(db_session, institution_id=a_id)
    assert bills_a == []
