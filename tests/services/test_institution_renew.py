"""机构批量续费 service 测试（D-124）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Order
from app.models.d14_v2_semesters import PurchasedSemester
from app.services import institution_renew_service as svc


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
    """seed 一个学生 + 一张 purchased_semesters（服务已迁移为基于该表）。"""
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student", nickname="学生"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    order = Order(
        id=uuid.uuid4(), order_no=f"on:{uuid.uuid4()}", payer_id=uid,
        beneficiary_id=uid, order_type="new", tier=tier, duration_months=6,
        amount_fen=7900, status="paid")
    s.add(order)
    await s.flush()
    s.add(PurchasedSemester(
        id=uuid.uuid4(), user_id=uid, textbook_version="renjiao", grade="七年级",
        semester="上", tier=tier, semester_no=1, started_at=now,
        expires_at=now + dt.timedelta(days=days_to_expire), order_id=order.id))
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


async def _latest_semester_expiry(s, user_id):
    return (await s.execute(
        select(PurchasedSemester.expires_at)
        .where(PurchasedSemester.user_id == user_id)
        .order_by(PurchasedSemester.expires_at.desc())
        .limit(1)
    )).scalar_one()


@pytest.mark.asyncio
async def test_batch_renew_extends_expiry(db_session):
    inst = await _inst(db_session)
    sid = await _student_with_membership(db_session, inst.id, tier="pro", days_to_expire=10)
    before = await _latest_semester_expiry(db_session, sid)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await db_session.flush()
    res = await svc.batch_renew(db_session, institution_id=inst.id,
                                student_ids=[sid], duration_months=6, operator_id=admin)
    assert res["renewed_count"] == 1
    # 服务按学期计价：duration_months=6 → 1 学期；pro = 7900 分/学期
    assert res["total_amount_fen"] == 7900
    after = await _latest_semester_expiry(db_session, sid)
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
