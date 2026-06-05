"""激活码兑换 service 测试（D-122）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Student, User
from app.services import activation_service, institution_purchase_service as psvc
from app.services import membership_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _setup(db_session):
    inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    db_session.add(inst)
    await db_session.flush()
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    sid = uuid.uuid4()
    db_session.add(User(id=sid, openid=f"o:{sid}", role="student"))
    await db_session.flush()
    db_session.add(Student(id=sid))
    await db_session.flush()
    _, codes = await psvc.create_purchase(
        db_session, institution_id=inst.id, created_by=admin,
        tier="pro", duration_months=6, quantity=1)
    return inst.id, sid, codes[0].code


@pytest.mark.asyncio
async def test_activate_code_grants_membership(db_session):
    inst_id, sid, code = await _setup(db_session)
    await activation_service.activate_code(db_session, student_user_id=sid, code=code)
    m = await membership_service.get_active_membership(db_session, user_id=sid)
    assert m is not None and str(m.tier) == "pro"
    stu = await db_session.get(Student, sid)
    assert stu.institution_id == inst_id


@pytest.mark.asyncio
async def test_activate_used_code_rejected(db_session):
    _, sid, code = await _setup(db_session)
    await activation_service.activate_code(db_session, student_user_id=sid, code=code)
    sid2 = uuid.uuid4()
    db_session.add(User(id=sid2, openid=f"o:{sid2}", role="student"))
    await db_session.flush()
    db_session.add(Student(id=sid2))
    await db_session.flush()
    with pytest.raises(AppError):
        await activation_service.activate_code(db_session, student_user_id=sid2, code=code)


@pytest.mark.asyncio
async def test_activate_creates_student_row_if_missing(db_session):
    # 普通微信学生：role=student 但无 students 行（plain wx 登录）
    inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    db_session.add(inst)
    await db_session.flush()
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    sid = uuid.uuid4()
    db_session.add(User(id=sid, openid=f"o:{sid}", role="student"))  # 不建 Student 行
    await db_session.flush()
    _, codes = await psvc.create_purchase(
        db_session, institution_id=inst.id, created_by=admin,
        tier="pro", duration_months=6, quantity=1)
    await activation_service.activate_code(db_session, student_user_id=sid, code=codes[0].code)
    stu = await db_session.get(Student, sid)
    assert stu is not None and stu.institution_id == inst.id
    m = await membership_service.get_active_membership(db_session, user_id=sid)
    assert m is not None and str(m.tier) == "pro"


@pytest.mark.asyncio
async def test_activate_bad_code(db_session):
    _, sid, _ = await _setup(db_session)
    with pytest.raises(AppError):
        await activation_service.activate_code(db_session, student_user_id=sid, code="ZZZZZZZZZZZZ")
