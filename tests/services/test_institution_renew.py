"""机构批量续费 service 测试（D-124）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.services import institution_renew_service as svc
from app.services import membership_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    return inst


async def _student_with_membership(s, inst_id, *, tier="pro", days_to_expire=10):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student", nickname="学生"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(
        id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
        expires_at=now + dt.timedelta(days=days_to_expire), is_active=True))
    await s.flush()
    return uid


async def _student_no_membership(s, inst_id):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_list_renewable_only_members(db_session):
    inst = await _inst(db_session)
    m = await _student_with_membership(db_session, inst.id)
    await _student_no_membership(db_session, inst.id)
    rows = await svc.list_renewable_students(db_session, institution_id=inst.id)
    ids = [r[0] for r in rows]
    assert m in ids and len(rows) == 1


@pytest.mark.asyncio
async def test_list_expiring_filter(db_session):
    inst = await _inst(db_session)
    near = await _student_with_membership(db_session, inst.id, days_to_expire=10)
    await _student_with_membership(db_session, inst.id, days_to_expire=200)
    rows = await svc.list_renewable_students(db_session, institution_id=inst.id, expiring_days=30)
    ids = [r[0] for r in rows]
    assert near in ids and len(rows) == 1


@pytest.mark.asyncio
async def test_batch_renew_extends_expiry(db_session):
    inst = await _inst(db_session)
    sid = await _student_with_membership(db_session, inst.id, tier="pro", days_to_expire=10)
    before = (await membership_service.get_active_membership(db_session, user_id=sid)).expires_at
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await db_session.flush()
    res = await svc.batch_renew(db_session, institution_id=inst.id,
                                student_ids=[sid], duration_months=6, operator_id=admin)
    assert res["renewed_count"] == 1
    assert res["total_amount_fen"] == 3000 * 6
    after = (await membership_service.get_active_membership(db_session, user_id=sid)).expires_at
    assert after > before


@pytest.mark.asyncio
async def test_batch_renew_skips_invalid(db_session):
    inst = await _inst(db_session)
    other = await _inst(db_session, "B")
    no_mem = await _student_no_membership(db_session, inst.id)
    b_member = await _student_with_membership(db_session, other.id)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await db_session.flush()
    res = await svc.batch_renew(db_session, institution_id=inst.id,
                                student_ids=[no_mem, b_member], duration_months=1, operator_id=admin)
    assert res["renewed_count"] == 0
    assert set(res["skipped"]) == {no_mem, b_member}
