"""机构后台 service 测试（D-120）：数据概览 + 资料 + 跨机构隔离。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, Teacher, User
from app.models.d2_payments import Membership
from app.models.d5_learning import StudyCheckin
from app.services import institution_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _institution(s, name="A机构") -> Institution:
    inst = Institution(
        id=uuid.uuid4(), name=name, contact_phone="13800000000",
        province_code="11", city_code="1101", address=f"{name}街",
    )
    s.add(inst)
    await s.flush()
    return inst


async def _teacher(s, inst_id):
    tid = uuid.uuid4()
    s.add(User(id=tid, openid=f"o:{tid}", role="teacher"))
    await s.flush()
    s.add(Teacher(id=tid, institution_id=inst_id))
    await s.flush()


async def _student(s, inst_id, *, member=False, active=False):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    await s.flush()
    if member:
        s.add(Membership(
            id=uuid.uuid4(), user_id=uid, tier="pro",
            started_at=dt.datetime.now(dt.timezone.utc), is_active=True,
        ))
    if active:
        s.add(StudyCheckin(
            id=uuid.uuid4(), student_id=uid, checkin_date=dt.date.today(),
            new_words_count=5, review_done=True, streak_days=1,
        ))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_get_overview_counts(db_session):
    inst = await _institution(db_session)
    await _teacher(db_session, inst.id)
    await _teacher(db_session, inst.id)
    # 3 学生：1 付费会员+活跃、1 仅活跃、1 普通
    await _student(db_session, inst.id, member=True, active=True)
    await _student(db_session, inst.id, active=True)
    await _student(db_session, inst.id)

    ov = await institution_service.get_overview(db_session, institution_id=inst.id)
    assert ov["teacher_count"] == 2
    assert ov["student_count"] == 3
    assert ov["member_count"] == 1
    assert ov["active_7d_count"] == 2
    # 新增字段存在（D-126）
    assert {"expiring_30d_count", "tier_distribution", "month_purchase_fen"} <= set(ov)


@pytest.mark.asyncio
async def test_get_overview_enhanced(db_session):
    from app.models.d2_payments import InstitutionPurchase
    inst = await _institution(db_session)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin",
                        institution_id=inst.id))
    await db_session.flush()
    # 3 个 pro 会员（_student member=True → tier=pro，expires_at=None）
    await _student(db_session, inst.id, member=True)
    await _student(db_session, inst.id, member=True)
    await _student(db_session, inst.id, member=True)
    # 本月采购
    db_session.add(InstitutionPurchase(
        id=uuid.uuid4(), institution_id=inst.id, tier="pro",
        duration_months=6, quantity=2, amount_fen=36000, status="paid",
        created_by=admin))
    await db_session.flush()

    ov = await institution_service.get_overview(db_session, institution_id=inst.id)
    assert ov["tier_distribution"] == {"basic": 0, "pro": 3, "promax": 0}
    assert ov["month_purchase_fen"] == 36000
    assert isinstance(ov["expiring_30d_count"], int)


@pytest.mark.asyncio
async def test_overview_isolated_between_institutions(db_session):
    a = await _institution(db_session, name="A")
    b = await _institution(db_session, name="B")
    await _student(db_session, a.id)
    await _student(db_session, b.id)
    await _student(db_session, b.id)

    ov_a = await institution_service.get_overview(db_session, institution_id=a.id)
    assert ov_a["student_count"] == 1  # 不含 B 的 2 个


@pytest.mark.asyncio
async def test_update_profile(db_session):
    inst = await _institution(db_session, name="旧名")
    updated = await institution_service.update_profile(
        db_session, institution_id=inst.id,
        name="新名", contact_phone="222", address="新址",
    )
    assert updated.name == "新名"
    assert updated.contact_phone == "222"
    assert updated.address == "新址"
