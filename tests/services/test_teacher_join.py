"""老师输码加入机构 service 测试（D-121）。"""
import datetime as dt
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, InviteCode, Teacher, User
from app.services import teacher_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _setup(s):
    inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    admin = uuid.uuid4()
    s.add(User(id=admin, openid=f"o:{admin}", role="institution_admin",
               institution_id=inst.id))
    tid = uuid.uuid4()
    s.add(User(id=tid, openid=f"o:{tid}", role="teacher"))
    await s.flush()
    s.add(Teacher(id=tid))
    s.add(InviteCode(id=uuid.uuid4(), code="ABC123", type="institution_join",
                     issuer_id=admin, target_id=None,
                     expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)))
    await s.flush()
    return inst, tid


@pytest.mark.asyncio
async def test_join_institution_ok(db_session):
    inst, tid = await _setup(db_session)
    t = await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ABC123")
    assert t.institution_id == inst.id
    code = (await db_session.execute(
        select(InviteCode).where(InviteCode.code == "ABC123")
    )).scalar_one()
    assert code.used_at is not None


@pytest.mark.asyncio
async def test_join_bad_code(db_session):
    _, tid = await _setup(db_session)
    with pytest.raises(AppError):
        await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ZZZZZZ")


@pytest.mark.asyncio
async def test_join_when_already_in_institution(db_session):
    inst, tid = await _setup(db_session)
    await teacher_service.join_institution(db_session, teacher_user_id=tid, code="ABC123")
    admin2 = (await db_session.execute(
        select(User).where(User.role == "institution_admin")
    )).scalars().first()
    db_session.add(InviteCode(id=uuid.uuid4(), code="DEF456", type="institution_join",
                              issuer_id=admin2.id, target_id=None,
                              expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)))
    await db_session.flush()
    with pytest.raises(AppError):
        await teacher_service.join_institution(db_session, teacher_user_id=tid, code="DEF456")
