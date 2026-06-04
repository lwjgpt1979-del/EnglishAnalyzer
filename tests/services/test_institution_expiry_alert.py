"""机构会员到期预警 service 测试（D-127）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d1_users import Institution, Student, User
from app.models.d2_payments import Membership
from app.models.d9_system import Notification
from app.services import institution_expiry_alert_service as svc


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
    return inst.id


async def _admin(s, inst_id):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="institution_admin", institution_id=inst_id))
    await s.flush()
    return uid


async def _student_expiring(s, inst_id, *, days_to_expire=10, tier="pro"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="student"))
    await s.flush()
    s.add(Student(id=uid, institution_id=inst_id))
    now = dt.datetime.now(dt.timezone.utc)
    s.add(Membership(id=uuid.uuid4(), user_id=uid, tier=tier, started_at=now,
                     expires_at=now + dt.timedelta(days=days_to_expire), is_active=True))
    await s.flush()
    return uid


async def _notifs_for(s, user_id):
    return (await s.execute(
        select(Notification).where(Notification.user_id == user_id)
    )).scalars().all()


@pytest.mark.asyncio
async def test_alert_emitted_when_expiring(db_session):
    # 断言具体管理员收到通知（service 扫全库，res 全局计数受其他已提交数据影响，不可靠）
    inst = await _inst(db_session)
    admin = await _admin(db_session, inst)
    await _student_expiring(db_session, inst, days_to_expire=10)
    await svc.run_expiry_alerts(db_session, days=30)
    notifs = await _notifs_for(db_session, admin)
    assert len(notifs) == 1
    assert str(notifs[0].type) == "membership"


@pytest.mark.asyncio
async def test_no_alert_when_none_expiring(db_session):
    inst = await _inst(db_session)
    admin = await _admin(db_session, inst)
    await _student_expiring(db_session, inst, days_to_expire=200)
    await svc.run_expiry_alerts(db_session, days=30)
    assert await _notifs_for(db_session, admin) == []


@pytest.mark.asyncio
async def test_isolated_and_multi_admin(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    a1 = await _admin(db_session, a)
    a2 = await _admin(db_session, a)
    b1 = await _admin(db_session, b)
    await _student_expiring(db_session, a, days_to_expire=5)
    res = await svc.run_expiry_alerts(db_session, days=30)
    assert len(await _notifs_for(db_session, a1)) == 1
    assert len(await _notifs_for(db_session, a2)) == 1
    assert await _notifs_for(db_session, b1) == []
